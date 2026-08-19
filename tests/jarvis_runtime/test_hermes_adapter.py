from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from jarvis.runtime import ConversationEntry, HermesBridgeConfig, HermesRuntimeAdapter, RuntimeEventType, TurnContext


FAKE_BRIDGE = Path(__file__).parents[1] / "fixtures" / "hermes_fake_bridge.py"
TERMINAL = {RuntimeEventType.TURN_COMPLETED, RuntimeEventType.TURN_FAILED, RuntimeEventType.TURN_CANCELLED}


def _adapter(scenario: str, *, timeout: float = 2, extra_env: dict[str, str] | None = None, max_line: int = 1024) -> HermesRuntimeAdapter:
    environment = {"FAKE_HERMES_SCENARIO": scenario}
    environment.update(extra_env or {})
    return HermesRuntimeAdapter(
        HermesBridgeConfig(
            command=(sys.executable, str(FAKE_BRIDGE)),
            environment=environment,
            timeout_seconds=timeout,
            interrupt_grace_seconds=0.1,
            terminate_grace_seconds=0.1,
            max_line_bytes=max_line,
            max_stderr_bytes=128,
        )
    )


async def _collect(adapter: HermesRuntimeAdapter, context: TurnContext):
    await adapter.start_turn(context)
    return [event async for event in adapter.stream_events(context.turn_id)]


@pytest.mark.parametrize(
    ("scenario", "terminal", "error_code"),
    [
        ("normal", RuntimeEventType.TURN_COMPLETED, None),
        ("slow", RuntimeEventType.TURN_COMPLETED, None),
        ("malformed", RuntimeEventType.TURN_FAILED, "bridge_malformed_output"),
        ("invalid", RuntimeEventType.TURN_FAILED, "bridge_invalid_event"),
        ("crash", RuntimeEventType.TURN_FAILED, "bridge_nonzero_exit"),
        ("nonzero", RuntimeEventType.TURN_FAILED, "bridge_nonzero_exit"),
        ("stderr", RuntimeEventType.TURN_COMPLETED, None),
        ("duplicate", RuntimeEventType.TURN_FAILED, "bridge_invalid_event"),
    ],
)
def test_bridge_scenarios_are_normalized(scenario: str, terminal: RuntimeEventType, error_code: str | None) -> None:
    events = asyncio.run(_collect(_adapter(scenario), TurnContext(uuid4(), (), "synthetic")))
    assert events[-1].type == terminal
    assert events[-1].error_code == error_code
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert sum(event.type in TERMINAL for event in events) == 1
    assert all("private-noise" not in (event.delta or "") for event in events)


def test_oversized_line_fails_safely() -> None:
    events = asyncio.run(_collect(_adapter("oversized", max_line=128), TurnContext(uuid4(), (), "synthetic")))
    assert events[-1].type == RuntimeEventType.TURN_FAILED
    assert events[-1].error_code == "bridge_line_too_large"


def test_timeout_fails_without_partial_message() -> None:
    events = asyncio.run(_collect(_adapter("timeout", timeout=0.05), TurnContext(uuid4(), (), "synthetic")))
    assert events[-1].type == RuntimeEventType.TURN_FAILED
    assert events[-1].error_code == "runtime_timeout"
    assert all(event.type != RuntimeEventType.MESSAGE_DELTA for event in events)


def test_cancel_is_real_and_idempotent() -> None:
    async def scenario():
        adapter = _adapter("cancel")
        context = TurnContext(uuid4(), (), "synthetic")
        await adapter.start_turn(context)
        stream = adapter.stream_events(context.turn_id)
        first = await anext(stream)
        await adapter.cancel_turn(context.turn_id)
        await adapter.cancel_turn(context.turn_id)
        return [first, *[event async for event in stream]]

    events = asyncio.run(scenario())
    assert events[-1].type == RuntimeEventType.TURN_CANCELLED
    assert sum(event.type in TERMINAL for event in events) == 1


@pytest.mark.parametrize("scenario", ["child", "cancel_child"])
def test_exact_turn_process_group_children_are_cleaned(tmp_path: Path, scenario: str) -> None:
    async def run():
        pid_file = tmp_path / "child.pid"
        adapter = _adapter(scenario, extra_env={"FAKE_HERMES_CHILD_PID": str(pid_file)})
        context = TurnContext(uuid4(), (), "synthetic")
        await adapter.start_turn(context)
        stream = adapter.stream_events(context.turn_id)
        first = await anext(stream)
        while not pid_file.exists():
            await asyncio.sleep(0.005)
        if scenario == "cancel_child":
            await adapter.cancel_turn(context.turn_id)
        events = [first, *[event async for event in stream]]
        return int(pid_file.read_text()), events

    child_pid, events = asyncio.run(run())
    try:
        state = Path(f"/proc/{child_pid}/stat").read_text().split()[2]
    except FileNotFoundError:
        state = None
    assert state in {None, "Z"}
    expected = RuntimeEventType.TURN_CANCELLED if scenario == "cancel_child" else RuntimeEventType.TURN_COMPLETED
    assert events[-1].type == expected


def test_canonical_history_request_has_current_user_exactly_once(tmp_path: Path) -> None:
    capture = tmp_path / "request.json"
    context = TurnContext(
        uuid4(),
        (ConversationEntry("user", "first"), ConversationEntry("assistant", "second")),
        "current unique marker",
    )
    events = asyncio.run(_collect(_adapter("normal", extra_env={"FAKE_HERMES_CAPTURE": str(capture)}), context))
    request = json.loads(capture.read_text())
    assert request["history"] == [{"role": "user", "content": "first"}, {"role": "assistant", "content": "second"}]
    assert request["current_user_message"] == "current unique marker"
    assert json.dumps(request).count("current unique marker") == 1
    assert events[-1].type == RuntimeEventType.TURN_COMPLETED


def test_adapter_does_not_inherit_parent_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_DATABASE_URL", "must-not-cross-boundary")
    adapter = _adapter("normal")
    assert "JARVIS_DATABASE_URL" not in adapter._config.environment


def test_request_limit_is_enforced_before_spawn() -> None:
    adapter = HermesRuntimeAdapter(
        HermesBridgeConfig(command=(sys.executable, str(FAKE_BRIDGE)), max_request_bytes=32)
    )
    with pytest.raises(ValueError, match="runtime_request_too_large"):
        asyncio.run(adapter.start_turn(TurnContext(uuid4(), (), "x" * 100)))
