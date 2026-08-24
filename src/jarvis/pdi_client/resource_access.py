from __future__ import annotations

import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

import httpx

RESOURCE_REF = re.compile(r"^pdi:resource:[0-9a-fA-F-]{36}$")
LIMITS = {"thumbnail": 2 * 1024 * 1024, "preview": 16 * 1024 * 1024}
BYTE_RANGE = re.compile(r"bytes=(?:[0-9]+-[0-9]*|-[0-9]+)")
CONTENT_RANGE = re.compile(r"bytes (?:[0-9]+-[0-9]+/[0-9]+|\*/[0-9]+)")


class RepresentationError(RuntimeError):
    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code); self.code = code; self.status_code = status_code


@dataclass(frozen=True, slots=True)
class RepresentationStream:
    content_type: str
    content_length: int | None
    body: AsyncIterator[bytes]


@dataclass(frozen=True, slots=True)
class VideoStream:
    status_code: int
    content_type: str | None
    content_length: int | None
    content_range: str | None
    accept_ranges: str | None
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

    @asynccontextmanager
    async def stream_video(
        self,
        resource_ref: str,
        byte_range: str | None = None,
    ) -> AsyncIterator[VideoStream]:
        if not RESOURCE_REF.fullmatch(resource_ref):
            raise RepresentationError("invalid_resource_ref", 400)
        if byte_range is not None and not BYTE_RANGE.fullmatch(byte_range):
            raise RepresentationError("unsupported_range", 416)
        if not self._socket_path and self._transport is None:
            raise RepresentationError("video_unavailable", 503)

        transport = self._transport or httpx.AsyncHTTPTransport(
            uds=self._socket_path
        )
        headers = {"Range": byte_range} if byte_range is not None else None
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://resource-access",
            timeout=self._timeout,
        ) as client:
            try:
                async with client.stream(
                    "GET",
                    f"/v1/resources/{resource_ref}/video",
                    headers=headers,
                ) as response:
                    if response.status_code == 404:
                        raise RepresentationError("video_unavailable", 404)
                    if response.status_code not in (200, 206, 416):
                        raise RepresentationError("video_unavailable", 503)

                    content_type: str | None = None
                    if response.status_code != 416:
                        raw_content_type = response.headers.get(
                            "content-type", ""
                        )
                        content_type = raw_content_type.split(";", 1)[0]
                        if not content_type.startswith("video/"):
                            raise RepresentationError(
                                "video_invalid", 502
                            )

                    length_header = response.headers.get("content-length")
                    content_length = (
                        int(length_header)
                        if length_header and length_header.isdigit()
                        else None
                    )
                    content_range = response.headers.get("content-range")
                    if (
                        content_range is not None
                        and not CONTENT_RANGE.fullmatch(content_range)
                    ):
                        raise RepresentationError("video_invalid", 502)
                    if (
                        response.status_code in (206, 416)
                        and content_range is None
                    ):
                        raise RepresentationError("video_invalid", 502)

                    accept_ranges = response.headers.get("accept-ranges")
                    if (
                        accept_ranges is not None
                        and accept_ranges.lower() != "bytes"
                    ):
                        raise RepresentationError("video_invalid", 502)

                    async def streaming() -> AsyncIterator[bytes]:
                        if response.status_code == 416:
                            return
                        async for chunk in response.aiter_bytes():
                            if chunk:
                                yield chunk

                    yield VideoStream(
                        response.status_code,
                        content_type,
                        content_length,
                        content_range,
                        "bytes" if accept_ranges is not None else None,
                        streaming(),
                    )
            except RepresentationError:
                raise
            except (httpx.HTTPError, OSError) as error:
                raise RepresentationError("video_unavailable", 503) from error
