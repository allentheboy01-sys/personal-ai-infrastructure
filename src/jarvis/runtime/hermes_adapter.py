from __future__ import annotations

import asyncio
import json
import os
import signal
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from uuid import UUID

from .contract import RuntimeEvent, RuntimeEventType, RuntimePhase, TurnContext


_TERMINAL = {
    RuntimeEventType.TURN_COMPLETED,
    RuntimeEventType.TURN_FAILED,
    RuntimeEventType.TURN_CANCELLED,
}
_RECORD_TYPES = {"ready", "phase", "delta", "completed", "failed", "cancelled"}


@dataclass(frozen=True, slots=True)
class HermesBridgeConfig:
    """Deployment-supplied command and bounds for the private Hermes bridge."""

    command: tuple[str, ...]
    environment: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    cwd: Path | None = None
    timeout_seconds: float = 600.0
    interrupt_grace_seconds: float = 2.0
    terminate_grace_seconds: float = 2.0
    max_request_bytes: int = 1_048_576
    max_line_bytes: int = 262_144
    max_stderr_bytes: int = 65_536
    max_visible_bytes: int = 4_194_304

    def __post_init__(self) -> None:
        if not self.command or any(not part for part in self.command):
            raise ValueError("bridge command must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("runtime timeout must be positive")
        if self.interrupt_grace_seconds < 0 or self.terminate_grace_seconds < 0:
            raise ValueError("process grace periods must not be negative")
        for value in (
            self.max_request_bytes,
            self.max_line_bytes,
            self.max_stderr_bytes,
            self.max_visible_bytes,
        ):
            if value <= 0:
                raise ValueError("bridge limits must be positive")


@dataclass(slots=True)
class _HermesTurn:
    queue: asyncio.Queue[RuntimeEvent] = field(default_factory=asyncio.Queue)
    task: asyncio.Task[None] | None = None
    process: asyncio.subprocess.Process | None = None
    cancel_requested: bool = False
    terminal: RuntimeEventType | None = None


class HermesRuntimeAdapter:
    """One isolated Hermes bridge subprocess per canonical Jarvis Turn."""

    def __init__(self, config: HermesBridgeConfig) -> None:
        self._config = config
        self._turns: dict[UUID, _HermesTurn] = {}

    async def start_turn(self, context: TurnContext) -> None:
        if context.turn_id in self._turns:
            raise RuntimeError("turn already started")
        request = _encode_request(context)
        if len(request) > self._config.max_request_bytes:
            raise ValueError("runtime_request_too_large")
        turn = _HermesTurn()
        self._turns[context.turn_id] = turn
        turn.task = asyncio.create_task(self._run(context.turn_id, request, turn))

    async def cancel_turn(self, turn_id: UUID) -> None:
        turn = self._turns.get(turn_id)
        if turn is None or turn.terminal is not None or turn.cancel_requested:
            return
        turn.cancel_requested = True
        process = turn.process
        if process is not None and process.returncode is None:
            try:
                process.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass
            await _cancel_after_grace(
                process,
                interrupt_grace=self._config.interrupt_grace_seconds,
                terminate_grace=self._config.terminate_grace_seconds,
            )

    async def stream_events(self, turn_id: UUID) -> AsyncIterator[RuntimeEvent]:
        turn = self._turns[turn_id]
        while True:
            event = await turn.queue.get()
            yield event
            if event.type in _TERMINAL:
                return

    async def _run(self, turn_id: UUID, request: bytes, turn: _HermesTurn) -> None:
        sequence = 0
        visible_bytes = 0
        stderr_task: asyncio.Task[bytes] | None = None
        process: asyncio.subprocess.Process | None = None
        completion_received = False
        ready_received = False
        terminal_event: RuntimeEvent | None = None

        async def emit(
            event_type: RuntimeEventType,
            *,
            phase: RuntimePhase | None = None,
            delta: str | None = None,
            error_code: str | None = None,
        ) -> None:
            nonlocal sequence, terminal_event
            if turn.terminal is not None:
                return
            sequence += 1
            event = RuntimeEvent(turn_id, sequence, event_type, phase=phase, delta=delta, error_code=error_code)
            if event_type in _TERMINAL:
                turn.terminal = event_type
                terminal_event = event
            else:
                await turn.queue.put(event)

        try:
            process = await asyncio.create_subprocess_exec(
                *self._config.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._config.cwd,
                env=dict(self._config.environment),
                start_new_session=True,
                limit=self._config.max_line_bytes + 1,
            )
            turn.process = process
            if turn.cancel_requested and process.returncode is None:
                process.send_signal(signal.SIGINT)
                asyncio.create_task(
                    _cancel_after_grace(
                        process,
                        interrupt_grace=self._config.interrupt_grace_seconds,
                        terminate_grace=self._config.terminate_grace_seconds,
                    )
                )
            assert process.stdin is not None
            assert process.stdout is not None
            assert process.stderr is not None
            stderr_task = asyncio.create_task(_capture_bounded(process.stderr, self._config.max_stderr_bytes))
            process.stdin.write(request + b"\n")
            await process.stdin.drain()
            process.stdin.close()

            async with asyncio.timeout(self._config.timeout_seconds):
                while True:
                    try:
                        raw = await process.stdout.readline()
                    except (ValueError, asyncio.LimitOverrunError) as error:
                        raise _BridgeError("bridge_line_too_large") from error
                    if not raw:
                        break
                    if len(raw) > self._config.max_line_bytes:
                        raise _BridgeError("bridge_line_too_large")
                    record = _parse_record(raw)
                    kind = record["type"]
                    if kind == "ready":
                        if ready_received:
                            raise _BridgeError("bridge_invalid_event")
                        ready_received = True
                        await emit(RuntimeEventType.TURN_STARTED)
                    elif not ready_received:
                        raise _BridgeError("bridge_invalid_event")
                    elif kind == "phase":
                        await emit(RuntimeEventType.PHASE_CHANGED, phase=RuntimePhase(record["phase"]))
                    elif kind == "delta":
                        delta = record["text"]
                        visible_bytes += len(delta.encode("utf-8"))
                        if visible_bytes > self._config.max_visible_bytes:
                            raise _BridgeError("runtime_output_too_large")
                        if delta:
                            await emit(RuntimeEventType.MESSAGE_DELTA, delta=delta)
                    elif kind == "completed":
                        if completion_received:
                            raise _BridgeError("bridge_invalid_event")
                        completion_received = True
                    elif kind == "failed":
                        await emit(RuntimeEventType.TURN_FAILED, error_code=_sanitize_error_code(record.get("code")))
                    elif kind == "cancelled":
                        await emit(RuntimeEventType.TURN_CANCELLED)
            return_code = await process.wait()
            if turn.terminal is None:
                if turn.cancel_requested:
                    await emit(RuntimeEventType.TURN_CANCELLED)
                elif completion_received and return_code == 0:
                    await emit(RuntimeEventType.TURN_COMPLETED)
                elif return_code != 0:
                    await emit(RuntimeEventType.TURN_FAILED, error_code="bridge_nonzero_exit")
                else:
                    await emit(RuntimeEventType.TURN_FAILED, error_code="bridge_exited")
        except TimeoutError:
            await emit(RuntimeEventType.TURN_FAILED, error_code="runtime_timeout")
        except _BridgeError as error:
            await emit(RuntimeEventType.TURN_FAILED, error_code=error.code)
        except (OSError, asyncio.SubprocessError):
            await emit(RuntimeEventType.TURN_FAILED, error_code="bridge_start_failed")
        except Exception:
            await emit(RuntimeEventType.TURN_FAILED, error_code="bridge_protocol_failed")
        finally:
            if turn.terminal is None:
                await emit(
                    RuntimeEventType.TURN_CANCELLED if turn.cancel_requested else RuntimeEventType.TURN_FAILED,
                    error_code=None if turn.cancel_requested else "bridge_exited",
                )
            if process is not None:
                await _cleanup_process_group(
                    process,
                    interrupt_first=turn.cancel_requested,
                    interrupt_grace=self._config.interrupt_grace_seconds,
                    terminate_grace=self._config.terminate_grace_seconds,
                )
            if stderr_task is not None:
                try:
                    await stderr_task
                except Exception:
                    pass
            if terminal_event is not None:
                await turn.queue.put(terminal_event)


class _BridgeError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _encode_request(context: TurnContext) -> bytes:
    payload = {
        "version": 1,
        "turn_id": str(context.turn_id),
        "history": [{"role": item.role, "content": item.body} for item in context.history],
        "current_user_message": context.current_user_message,
        "attachment_refs": list(context.attachment_refs),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _parse_record(raw: bytes) -> dict[str, object]:
    try:
        record = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _BridgeError("bridge_malformed_output") from error
    if not isinstance(record, dict) or record.get("type") not in _RECORD_TYPES:
        raise _BridgeError("bridge_invalid_event")
    kind = record["type"]
    if kind == "phase" and record.get("phase") not in {phase.value for phase in RuntimePhase}:
        raise _BridgeError("bridge_invalid_event")
    if kind == "delta" and not isinstance(record.get("text"), str):
        raise _BridgeError("bridge_invalid_event")
    return record


def _sanitize_error_code(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 64:
        return "hermes_failed"
    if any(not (char.islower() or char.isdigit() or char == "_") for char in value):
        return "hermes_failed"
    return value


async def _capture_bounded(stream: asyncio.StreamReader, limit: int) -> bytes:
    captured = bytearray()
    while True:
        chunk = await stream.read(min(8192, limit + 1))
        if not chunk:
            return bytes(captured)
        remaining = limit - len(captured)
        if remaining > 0:
            captured.extend(chunk[:remaining])


async def _cleanup_process_group(
    process: asyncio.subprocess.Process,
    *,
    interrupt_first: bool,
    interrupt_grace: float,
    terminate_grace: float,
) -> None:
    pgid = process.pid
    if process.returncode is None and interrupt_first:
        try:
            process.send_signal(signal.SIGINT)
        except ProcessLookupError:
            pass
        if await _wait_process(process, interrupt_grace):
            await _terminate_remaining_group(pgid, terminate_grace)
            return
    if process.returncode is None:
        _signal_group(pgid, signal.SIGTERM)
        if not await _wait_process(process, terminate_grace):
            _signal_group(pgid, signal.SIGKILL)
            await process.wait()
    await _terminate_remaining_group(pgid, terminate_grace)


async def _cancel_after_grace(
    process: asyncio.subprocess.Process,
    *,
    interrupt_grace: float,
    terminate_grace: float,
) -> None:
    if await _wait_process(process, interrupt_grace):
        await _terminate_remaining_group(process.pid, terminate_grace)
        return
    _signal_group(process.pid, signal.SIGTERM)
    if not await _wait_process(process, terminate_grace):
        _signal_group(process.pid, signal.SIGKILL)
        await process.wait()


async def _terminate_remaining_group(pgid: int, grace: float) -> None:
    if not _group_exists(pgid):
        return
    _signal_group(pgid, signal.SIGTERM)
    deadline = asyncio.get_running_loop().time() + grace
    while _group_exists(pgid) and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.01)
    if _group_exists(pgid):
        _signal_group(pgid, signal.SIGKILL)
        deadline = asyncio.get_running_loop().time() + grace
        while _group_exists(pgid) and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)


async def _wait_process(process: asyncio.subprocess.Process, timeout: float) -> bool:
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout)
        return True
    except TimeoutError:
        return False


def _group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_group(pgid: int, sig: signal.Signals) -> None:
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass
