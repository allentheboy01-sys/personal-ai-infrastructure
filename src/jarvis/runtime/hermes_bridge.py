"""Private JSONL bridge executed by the isolated Hermes Python environment.

This file intentionally imports no Jarvis package. It is launched as a script
so the Hermes environment needs no PDI/Jarvis installation.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any


EXPECTED_PDI_TOOLS = (
    "pdi_list_recent_resources",
    "pdi_search_resources",
    "pdi_get_resource",
    "pdi_aggregate_resources",
    "pdi_get_resource_observations",
    "pdi_retrieve_resources",
    "pdi_rich_retrieve_resources",
)
MAX_REQUEST_BYTES = 1_048_576


class ProtocolWriter:
    def __init__(self) -> None:
        self._stream = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
        self._lock = threading.Lock()

    def emit(self, kind: str, **values: object) -> None:
        record = {"type": kind, **values}
        with self._lock:
            self._stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._stream.flush()


class VisibleDeltaFilter:
    """Suppress streamed <think> blocks, including tags split across chunks."""

    def __init__(self, emit) -> None:
        self._emit = emit
        self._buffer = ""
        self._thinking = False

    def feed(self, value: object) -> None:
        if not isinstance(value, str) or not value:
            return
        self._buffer += value
        self._drain(final=False)

    def finish(self) -> None:
        self._drain(final=True)

    def _drain(self, *, final: bool) -> None:
        while self._buffer:
            tag = "</think>" if self._thinking else "<think>"
            index = self._buffer.lower().find(tag)
            if index >= 0:
                if not self._thinking and index:
                    self._emit(self._buffer[:index])
                self._buffer = self._buffer[index + len(tag) :]
                self._thinking = not self._thinking
                continue
            if final:
                if not self._thinking:
                    self._emit(self._buffer)
                self._buffer = ""
                return
            keep = min(len(tag) - 1, len(self._buffer))
            safe_length = len(self._buffer) - keep
            if safe_length and not self._thinking:
                self._emit(self._buffer[:safe_length])
            self._buffer = self._buffer[safe_length:]
            return


def _load_request() -> dict[str, Any]:
    raw = sys.stdin.buffer.readline(MAX_REQUEST_BYTES + 2)
    if len(raw) > MAX_REQUEST_BYTES or not raw.endswith(b"\n"):
        raise ValueError("invalid_request")
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("invalid_request")
    history = value.get("history")
    current = value.get("current_user_message")
    if not isinstance(history, list) or not isinstance(current, str):
        raise ValueError("invalid_request")
    normalized = []
    for item in history:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"} or not isinstance(item.get("content"), str):
            raise ValueError("invalid_request")
        normalized.append({"role": item["role"], "content": item["content"]})
    value["history"] = normalized
    return value


def _phase_for_tool(name: object) -> str:
    lowered = str(name or "").lower()
    if any(token in lowered for token in ("search", "retrieve", "recent", "aggregate", "web")):
        return "searching"
    if any(token in lowered for token in ("resource", "observation", "read", "inspect", "view")):
        return "reviewing"
    if any(token in lowered for token in ("terminal", "python", "code", "shell", "calculate", "execute")):
        return "computing"
    return "thinking"


def _run() -> int:
    writer = ProtocolWriter()
    # Hermes and MCP code may print diagnostics. Keep protocol stdout pure.
    sys.stdout = sys.stderr
    request = _load_request()

    from hermes_cli.config import load_config
    from run_agent import AIAgent

    config = load_config() or {}
    model_config = config.get("model") or {}
    if isinstance(model_config, str):
        model = model_config
        provider = None
        base_url = None
    else:
        model = model_config.get("default") or model_config.get("model") or ""
        provider = model_config.get("provider")
        base_url = model_config.get("base_url")
    agent_config = config.get("agent") or {}
    platform_tools = config.get("platform_toolsets") or {}
    enabled_toolsets = platform_tools.get("cli") or config.get("toolsets") or None
    if isinstance(enabled_toolsets, str):
        enabled_toolsets = [part.strip() for part in enabled_toolsets.split(",") if part.strip()]

    cancel_requested = False
    agent: AIAgent | None = None
    last_phase: str | None = None

    def emit_phase(phase: str) -> None:
        nonlocal last_phase
        if phase != last_phase:
            writer.emit("phase", phase=phase)
            last_phase = phase

    def emit_text(text: str) -> None:
        if text:
            emit_phase("composing")
            writer.emit("delta", text=text)

    def interrupt(_signum, _frame) -> None:
        nonlocal cancel_requested
        cancel_requested = True
        if agent is not None:
            agent.interrupt()

    signal.signal(signal.SIGINT, interrupt)
    writer.emit("ready")
    emit_phase("thinking")
    try:
        agent = AIAgent(
            model=model,
            base_url=base_url,
            provider=provider,
            max_iterations=int(agent_config.get("max_turns") or 90),
            enabled_toolsets=enabled_toolsets,
            save_trajectories=False,
            verbose_logging=False,
            quiet_mode=True,
            ephemeral_system_prompt=agent_config.get("system_prompt") or None,
            reasoning_config=(config.get("reasoning") or None),
            # Hermes can stream assistant text from intermediate tool-loop
            # iterations. Only the final_response below is product-visible.
            stream_delta_callback=lambda _value: None,
            reasoning_callback=lambda *_args, **_kwargs: emit_phase("thinking"),
            thinking_callback=lambda *_args, **_kwargs: emit_phase("thinking"),
            tool_start_callback=lambda _tool_id, name, _args: emit_phase(_phase_for_tool(name)),
            tool_complete_callback=lambda _tool_id, name, _args, _result: emit_phase(_phase_for_tool(name)),
            session_db=None,
            persist_session=False,
            skip_memory=True,
            checkpoints_enabled=False,
            platform="jarvis-web",
        )
        result = agent.run_conversation(
            request["current_user_message"],
            conversation_history=request["history"],
            task_id=request.get("turn_id"),
        )
        if cancel_requested:
            writer.emit("cancelled")
            return 0
        if not isinstance(result, dict) or not result.get("completed"):
            writer.emit("failed", code="hermes_failed")
            return 1
        final = result.get("final_response")
        if not isinstance(final, str) or not final:
            writer.emit("failed", code="hermes_empty_response")
            return 1
        visible_parts: list[str] = []
        visible = VisibleDeltaFilter(visible_parts.append)
        visible.feed(final)
        visible.finish()
        safe_final = "".join(visible_parts)
        if not safe_final:
            writer.emit("failed", code="hermes_empty_response")
            return 1
        for offset in range(0, len(safe_final), 16_384):
            emit_text(safe_final[offset : offset + 16_384])
        writer.emit("completed")
        return 0
    except Exception:
        writer.emit("cancelled" if cancel_requested else "failed", **({} if cancel_requested else {"code": "hermes_failed"}))
        return 0 if cancel_requested else 1


def _check(profile: Path) -> int:
    result: dict[str, object] = {"compatible": False}
    try:
        import yaml
        from run_agent import AIAgent

        config = yaml.safe_load((profile / "config.yaml").read_text(encoding="utf-8")) or {}
        tools = tuple(config["mcp_servers"]["pdi"]["tools"]["include"])
        signature = inspect.signature(AIAgent)
        result = {
            "compatible": tools == EXPECTED_PDI_TOOLS,
            "aiagent": True,
            "interrupt": callable(getattr(AIAgent, "interrupt", None)),
            "run_conversation": callable(getattr(AIAgent, "run_conversation", None)),
            "callbacks": all(name in signature.parameters for name in ("stream_delta_callback", "reasoning_callback", "tool_start_callback", "tool_complete_callback")),
            "profile_readable": True,
            "pdi_tool_count": len(tools),
            "pdi_tools_match": tools == EXPECTED_PDI_TOOLS,
        }
    except Exception:
        result = {"compatible": False, "error_code": "compatibility_check_failed"}
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result.get("compatible") else 1


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--check-profile", type=Path)
    args = parser.parse_args()
    if args.check_profile is not None:
        return _check(args.check_profile)
    return _run()


if __name__ == "__main__":
    raise SystemExit(main())
