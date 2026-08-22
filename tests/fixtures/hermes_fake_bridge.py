from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


scenario = os.environ.get("FAKE_HERMES_SCENARIO", "normal")
request = json.loads(sys.stdin.readline())
capture = os.environ.get("FAKE_HERMES_CAPTURE")
if capture:
    Path(capture).write_text(json.dumps(request), encoding="utf-8")


def emit(kind: str, **values: object) -> None:
    print(json.dumps({"type": kind, **values}), flush=True)


def cancelled(_signum, _frame) -> None:
    emit("cancelled")
    raise SystemExit(0)


signal.signal(signal.SIGINT, cancelled)

if scenario == "malformed":
    print("not-json", flush=True)
elif scenario == "invalid":
    emit("raw_tool_result", payload="must-not-escape")
elif scenario == "oversized":
    print("x" * 4096, flush=True)
elif scenario == "nonzero":
    raise SystemExit(7)
elif scenario == "crash":
    emit("ready")
    raise SystemExit(2)
elif scenario == "stderr":
    sys.stderr.write("private-noise" * 10000)
    sys.stderr.flush()
    emit("ready")
    emit("delta", text="safe")
    emit("completed")
elif scenario == "timeout":
    emit("ready")
    time.sleep(60)
elif scenario == "cancel":
    emit("ready")
    emit("phase", phase="thinking")
    time.sleep(60)
elif scenario in {"child", "cancel_child"}:
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    Path(os.environ["FAKE_HERMES_CHILD_PID"]).write_text(str(child.pid), encoding="ascii")
    emit("ready")
    if scenario == "cancel_child":
        time.sleep(60)
    else:
        emit("delta", text="child result")
        emit("completed")
elif scenario == "duplicate":
    emit("ready")
    emit("delta", text="once")
    emit("completed")
    emit("completed")
elif scenario == "tools":
    emit("ready")
    emit("phase", phase="searching")
    emit("tool.started", operation_id=1, category="pdi", capability="search_personal_resources")
    emit("tool.completed", operation_id=1, category="pdi", capability="search_personal_resources", duration_ms=25)
    emit("phase", phase="computing")
    emit("tool.started", operation_id=2, category="exec", capability="run_python")
    emit("tool.completed", operation_id=2, category="exec", capability="run_python", duration_ms=40)
    emit("delta", text="safe")
    emit("completed")
elif scenario == "tool_invalid_category":
    emit("ready")
    emit("tool.started", operation_id=1, category="private", capability="use_tool")
elif scenario == "tool_extra_field":
    emit("ready")
    emit("tool.started", operation_id=1, category="other", capability="use_tool", arguments="private")
elif scenario == "tool_missing_field":
    emit("ready")
    emit("tool.started", operation_id=1, category="other")
elif scenario == "tool_unmatched":
    emit("ready")
    emit("tool.completed", operation_id=1, category="other", capability="use_tool", duration_ms=1)
elif scenario == "tool_nonmonotonic":
    emit("ready")
    emit("tool.started", operation_id=2, category="other", capability="use_tool")
elif scenario == "tool_invalid_duration":
    emit("ready")
    emit("tool.started", operation_id=1, category="other", capability="use_tool")
    emit("tool.completed", operation_id=1, category="other", capability="use_tool", duration_ms=600001)
elif scenario == "slow":
    emit("ready")
    emit("phase", phase="searching")
    time.sleep(0.05)
    emit("delta", text="slow ")
    time.sleep(0.05)
    emit("delta", text="answer")
    emit("completed")
else:
    emit("ready")
    emit("phase", phase="thinking")
    emit("phase", phase="searching")
    emit("phase", phase="composing")
    emit("delta", text="hello ")
    emit("delta", text="world")
    emit("completed")
