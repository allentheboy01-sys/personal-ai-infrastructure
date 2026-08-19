from __future__ import annotations

import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

import httpx

RESOURCE_REF = re.compile(r"^pdi:resource:[0-9a-fA-F-]{36}$")
LIMITS = {"thumbnail": 2 * 1024 * 1024, "preview": 16 * 1024 * 1024}


class RepresentationError(RuntimeError):
    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code); self.code = code; self.status_code = status_code


@dataclass(frozen=True, slots=True)
class RepresentationStream:
    content_type: str
    content_length: int | None
    body: AsyncIterator[bytes]


class ResourceAccessClient:
    def __init__(self, socket_path: str | None, *, timeout_seconds: float = 20.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._socket_path = socket_path
        self._timeout = timeout_seconds
        self._transport = transport

    @asynccontextmanager
    async def stream(self, resource_ref: str, kind: str) -> AsyncIterator[RepresentationStream]:
        if not RESOURCE_REF.fullmatch(resource_ref): raise RepresentationError("invalid_resource_ref", 400)
        if kind not in LIMITS: raise RepresentationError("unsupported_representation", 400)
        if not self._socket_path and self._transport is None: raise RepresentationError("representation_unavailable", 503)
        transport = self._transport or httpx.AsyncHTTPTransport(uds=self._socket_path)
        async with httpx.AsyncClient(transport=transport, base_url="http://resource-access", timeout=self._timeout) as client:
            try:
                async with client.stream("GET", f"/v1/resources/{resource_ref}/representations/{kind}") as response:
                    if response.status_code == 404: raise RepresentationError("representation_unavailable", 404)
                    if response.status_code != 200: raise RepresentationError("representation_unavailable", 503)
                    content_type = response.headers.get("content-type", "").split(";", 1)[0]
                    if not content_type.startswith("image/"): raise RepresentationError("representation_invalid", 502)
                    length_header = response.headers.get("content-length")
                    length = int(length_header) if length_header and length_header.isdigit() else None
                    limit = LIMITS[kind]
                    if length is not None and length > limit: raise RepresentationError("representation_too_large", 502)
                    async def bounded() -> AsyncIterator[bytes]:
                        seen = 0
                        async for chunk in response.aiter_bytes():
                            seen += len(chunk)
                            if seen > limit: raise RepresentationError("representation_too_large", 502)
                            yield chunk
                    yield RepresentationStream(content_type, length, bounded())
            except RepresentationError:
                raise
            except (httpx.HTTPError, OSError) as error:
                raise RepresentationError("representation_unavailable", 503) from error
