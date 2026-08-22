"""Raw full-duplex stdio bridge to the fixed Jarvis Exec AF_UNIX socket."""

from __future__ import annotations

import os
import socket
import sys
import threading

SOCKET_PATH = "/run/jarvis-exec.sock"


def _copy(source_fd: int, target_fd: int, *, shutdown: socket.socket | None = None) -> None:
    try:
        while chunk := os.read(source_fd, 65536):
            view = memoryview(chunk)
            while view:
                written = os.write(target_fd, view)
                view = view[written:]
    finally:
        if shutdown is not None:
            try:
                shutdown.shutdown(socket.SHUT_WR)
            except OSError:
                pass


def main() -> int:
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(10)
    try:
        connection.connect(SOCKET_PATH)
        connection.settimeout(None)
    except OSError:
        print("jarvis-exec-proxy: execution service unavailable", file=sys.stderr)
        return 1
    reader = threading.Thread(target=_copy, args=(connection.fileno(), sys.stdout.fileno()), daemon=True)
    reader.start()
    _copy(sys.stdin.fileno(), connection.fileno(), shutdown=connection)
    reader.join(timeout=5)
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
