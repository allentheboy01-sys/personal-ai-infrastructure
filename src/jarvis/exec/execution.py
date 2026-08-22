"""Bounded Python execution within the systemd-owned sandbox."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .contract import EXECUTION_TIMEOUT_SECONDS, MAX_STDERR_BYTES, MAX_STDOUT_BYTES


def _bounded(stream, limit: int) -> str:
    stream.seek(0)
    data = stream.read(limit + 1)
    suffix = b"\n[output truncated]" if len(data) > limit else b""
    return (data[:limit] + suffix).decode("utf-8", errors="replace")


def execute_python(code: str, workspace: Path) -> dict[str, object]:
    if not isinstance(code, str) or not code or len(code.encode("utf-8")) > 2 * 1024 * 1024:
        return {"status": "limit", "stdout": "", "stderr": "invalid_code"}
    environment = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(workspace),
    }
    started = time.monotonic()
    with tempfile.TemporaryFile(dir=workspace) as stdout, tempfile.TemporaryFile(dir=workspace) as stderr:
        process = subprocess.Popen(
            [sys.executable, "-I", "-B", "-c", code],
            cwd=workspace,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
            start_new_session=True,
        )
        status = "completed"
        try:
            return_code = process.wait(timeout=EXECUTION_TIMEOUT_SECONDS)
            if return_code != 0:
                status = "failed"
        except subprocess.TimeoutExpired:
            status = "timeout"
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
            return_code = None
        duration = time.monotonic() - started
        return {
            "status": status,
            "exit_code": return_code,
            "stdout": _bounded(stdout, MAX_STDOUT_BYTES),
            "stderr": _bounded(stderr, MAX_STDERR_BYTES),
            "duration": "under_1s" if duration < 1 else "under_30s" if duration < 30 else "limit",
        }
