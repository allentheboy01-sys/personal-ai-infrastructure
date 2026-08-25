"""One-request JSONL protocol over a private systemd AF_UNIX socket."""

from __future__ import annotations

import asyncio
import json
import os
import socket
from pathlib import Path

from .contract import MAX_IPC_REQUEST_BYTES, MAX_IPC_RESPONSE_BYTES, failure
from .service import WebAccessService


SOCKET_PATH = "/run/jarvis-web-access.sock"


class WebAccessIpcServer:
    def __init__(self, service: WebAccessService) -> None:
        self._service = service

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        result: dict[str, object] = failure("invalid_request")
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=2.0)
            if not raw.endswith(b"\n") or len(raw) > MAX_IPC_REQUEST_BYTES:
                raise ValueError
            request = json.loads(raw)
            if not isinstance(request, dict) or request.get("version") != 1:
                raise ValueError
            operation = request.get("operation")
            if operation == "search" and set(request) <= {"version", "operation", "query", "limit"}:
                result = await self._service.search(request.get("query"), request.get("limit", 5))
            elif operation == "fetch" and set(request) <= {"version", "operation", "url"}:
                result = await self._service.fetch(request.get("url"))
        except (TimeoutError, ValueError, json.JSONDecodeError, UnicodeError, asyncio.LimitOverrunError):
            result = failure("invalid_request")
        except Exception:
            result = failure("provider_unavailable")
        payload = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(payload) > MAX_IPC_RESPONSE_BYTES:
            payload = b'{"ok":false,"error":"body_too_large"}\n'
        writer.write(payload)
        try:
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()


async def serve_systemd(service: WebAccessService) -> None:
    inherited = int(os.environ.get("LISTEN_FDS", "0")) == 1 and int(os.environ.get("LISTEN_PID", "0")) == os.getpid()
    test_path = os.environ.get("JARVIS_WEB_ACCESS_TEST_SOCKET")
    handler = WebAccessIpcServer(service).handle
    if inherited:
        listener = socket.fromfd(3, socket.AF_UNIX, socket.SOCK_STREAM)
        listener.setblocking(False)
        server = await asyncio.start_unix_server(handler, sock=listener, limit=MAX_IPC_REQUEST_BYTES + 1)
    elif test_path:
        path = Path(test_path)
        path.unlink(missing_ok=True)
        server = await asyncio.start_unix_server(handler, path=path, limit=MAX_IPC_REQUEST_BYTES + 1)
    else:
        raise RuntimeError("web access socket unavailable")
    async with server:
        await server.serve_forever()
