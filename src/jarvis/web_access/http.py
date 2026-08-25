"""Minimal HTTP/1.1 transport that connects only to validated pinned IPs."""

from __future__ import annotations

import asyncio
import ipaddress
import ssl
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from urllib.parse import urljoin

from .contract import (
    CONNECT_TIMEOUT_SECONDS,
    FETCH_TIMEOUT_SECONDS,
    FIRST_BYTE_TIMEOUT_SECONDS,
    MAX_HEADER_BYTES,
    MAX_HEADER_COUNT,
    MAX_RAW_BODY_BYTES,
    MAX_REDIRECTS,
    READ_IDLE_TIMEOUT_SECONDS,
    WebAccessError,
)
from .security import PinnedTarget, PublicResolver, _normalized_ip


Connector = Callable[
    [str, int, ssl.SSLContext | None, str | None],
    Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]],
]


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str


async def _default_connector(
    address: str,
    port: int,
    context: ssl.SSLContext | None,
    server_hostname: str | None,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    return await asyncio.open_connection(
        host=address,
        port=port,
        ssl=context,
        server_hostname=server_hostname,
        ssl_handshake_timeout=CONNECT_TIMEOUT_SECONDS if context is not None else None,
        limit=MAX_HEADER_BYTES + 1,
    )


class PinnedHttpClient:
    """HTTP client with resolve-once pinning, peer verification and manual redirects."""

    def __init__(
        self,
        *,
        resolver: PublicResolver | None = None,
        connector: Connector = _default_connector,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self._resolver = resolver or PublicResolver()
        self._connector = connector
        self._ssl_context = ssl_context or ssl.create_default_context()

    async def get(self, url: str) -> HttpResponse:
        return await self.request("GET", url)

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes = b"",
        overall_timeout: float = FETCH_TIMEOUT_SECONDS,
    ) -> HttpResponse:
        if method not in {"GET", "POST"} or len(body) > 64 * 1024:
            raise WebAccessError("blocked_url")
        try:
            async with asyncio.timeout(overall_timeout):
                return await self._request_with_redirects(method, url, headers or {}, body)
        except WebAccessError:
            raise
        except (TimeoutError, asyncio.TimeoutError):
            raise WebAccessError("timeout") from None
        except (OSError, ssl.SSLError, asyncio.IncompleteReadError, UnicodeError, ValueError):
            raise WebAccessError("provider_unavailable") from None

    async def _request_with_redirects(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> HttpResponse:
        current = url
        previous_scheme: str | None = None
        for redirect_count in range(MAX_REDIRECTS + 1):
            pinned = await self._resolver.parse_and_resolve(current)
            if previous_scheme == "https" and pinned.parsed.scheme == "http":
                raise WebAccessError("redirect_blocked")
            response = await self._one_request(pinned, method, headers, body)
            if response.status not in {301, 302, 303, 307, 308}:
                return HttpResponse(response.status, response.headers, response.body, pinned.parsed.url)
            location = response.headers.get("location")
            if not location:
                raise WebAccessError("redirect_blocked")
            if redirect_count == MAX_REDIRECTS:
                raise WebAccessError("too_many_redirects")
            previous_scheme = pinned.parsed.scheme
            current = urljoin(pinned.parsed.url, location)
            if "authorization" in {name.lower() for name in headers}:
                redirected = self._resolver_url_for_origin_check(current)
                original_origin = (pinned.parsed.scheme, pinned.parsed.hostname, pinned.parsed.port)
                redirected_origin = (redirected.scheme, redirected.hostname, redirected.port)
                if redirected_origin != original_origin:
                    raise WebAccessError("redirect_blocked")
            if response.status == 303 and method == "POST":
                method, body, headers = "GET", b"", {}
        raise WebAccessError("too_many_redirects")

    @staticmethod
    def _resolver_url_for_origin_check(url: str):
        from .security import parse_public_url

        return parse_public_url(url)

    async def _one_request(
        self,
        pinned: PinnedTarget,
        method: str,
        extra_headers: Mapping[str, str],
        body: bytes,
    ) -> HttpResponse:
        reader: asyncio.StreamReader | None = None
        writer: asyncio.StreamWriter | None = None
        for address in pinned.addresses:
            context = self._ssl_context if pinned.parsed.scheme == "https" else None
            server_hostname = pinned.parsed.hostname if context is not None else None
            try:
                reader, writer = await asyncio.wait_for(
                    self._connector(str(address), pinned.parsed.port, context, server_hostname),
                    timeout=CONNECT_TIMEOUT_SECONDS,
                )
                self._verify_peer(writer, pinned)
                break
            except WebAccessError:
                if writer is not None:
                    writer.close()
                raise
            except (TimeoutError, OSError, ssl.SSLError):
                if writer is not None:
                    writer.close()
                reader, writer = None, None
        if reader is None or writer is None:
            raise WebAccessError("timeout")
        try:
            request = self._build_request(pinned, method, extra_headers, body)
            writer.write(request)
            await asyncio.wait_for(writer.drain(), timeout=CONNECT_TIMEOUT_SECONDS)
            header_block = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=FIRST_BYTE_TIMEOUT_SECONDS)
            if len(header_block) > MAX_HEADER_BYTES:
                raise WebAccessError("provider_unavailable")
            status, response_headers = self._parse_headers(header_block)
            if status in {301, 302, 303, 307, 308}:
                return HttpResponse(status, response_headers, b"", pinned.parsed.url)
            self._raise_for_status(status)
            encoding = response_headers.get("content-encoding", "").strip().lower()
            if encoding not in {"", "identity"}:
                raise WebAccessError("unsupported_content_encoding")
            response_body = await self._read_body(reader, response_headers)
            return HttpResponse(status, response_headers, response_body, pinned.parsed.url)
        except asyncio.LimitOverrunError:
            raise WebAccessError("provider_unavailable") from None
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, ssl.SSLError):
                pass

    @staticmethod
    def _verify_peer(writer: asyncio.StreamWriter, pinned: PinnedTarget) -> None:
        peer = writer.get_extra_info("peername")
        if not isinstance(peer, tuple) or not peer:
            raise WebAccessError("non_public_destination")
        try:
            actual = _normalized_ip(peer[0])
        except ValueError:
            raise WebAccessError("non_public_destination") from None
        if actual not in pinned.addresses:
            raise WebAccessError("non_public_destination")

    @staticmethod
    def _build_request(
        pinned: PinnedTarget,
        method: str,
        extra_headers: Mapping[str, str],
        body: bytes,
    ) -> bytes:
        controlled = {
            "user-agent": "Jarvis-Web-Access/0.1",
            "accept": "text/html, text/plain, text/markdown, application/xhtml+xml, application/json",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "accept-encoding": "identity",
            "connection": "close",
        }
        allowed_internal = {"authorization", "content-type", "accept"}
        for key, value in extra_headers.items():
            normalized = key.lower().strip()
            if normalized not in allowed_internal or "\r" in value or "\n" in value:
                raise WebAccessError("blocked_url")
            controlled[normalized] = value
        if body:
            controlled["content-length"] = str(len(body))
        lines = [f"{method} {pinned.parsed.target} HTTP/1.1", f"Host: {pinned.parsed.host_header}"]
        lines.extend(f"{name.title()}: {value}" for name, value in controlled.items())
        return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii") + body

    @staticmethod
    def _parse_headers(block: bytes) -> tuple[int, dict[str, str]]:
        try:
            lines = block[:-4].decode("iso-8859-1").split("\r\n")
            version, raw_status, _reason = lines[0].split(" ", 2)
            status = int(raw_status)
        except (ValueError, IndexError, UnicodeError):
            raise WebAccessError("provider_unavailable") from None
        if version not in {"HTTP/1.0", "HTTP/1.1"} or not 100 <= status <= 599 or len(lines) - 1 > MAX_HEADER_COUNT:
            raise WebAccessError("provider_unavailable")
        headers: dict[str, str] = {}
        singletons = {"content-length", "content-type", "content-encoding", "transfer-encoding", "location"}
        for line in lines[1:]:
            name, separator, value = line.partition(":")
            normalized = name.strip().lower()
            value = value.strip()
            if (
                not separator
                or not normalized
                or any(ord(char) < 0x21 or ord(char) > 0x7E for char in normalized)
                or any((ord(char) < 0x20 and char != "\t") or ord(char) == 0x7F for char in value)
            ):
                raise WebAccessError("provider_unavailable")
            if normalized in headers and normalized in singletons and headers[normalized] != value:
                raise WebAccessError("provider_unavailable")
            headers.setdefault(normalized, value)
        return status, headers

    @staticmethod
    def _raise_for_status(status: int) -> None:
        if 200 <= status < 300:
            return
        if status in {403, 404, 429}:
            raise WebAccessError(f"http_{status}")
        if 500 <= status <= 599:
            raise WebAccessError("http_5xx")
        raise WebAccessError("http_error")

    async def _read_body(self, reader: asyncio.StreamReader, headers: Mapping[str, str]) -> bytes:
        length_value = headers.get("content-length")
        transfer_encoding = headers.get("transfer-encoding", "").lower()
        if length_value is not None and transfer_encoding:
            raise WebAccessError("provider_unavailable")
        if transfer_encoding:
            if transfer_encoding != "chunked":
                raise WebAccessError("unsupported_content_encoding")
            return await self._read_chunked(reader)
        if length_value is not None:
            try:
                length = int(length_value)
            except ValueError:
                raise WebAccessError("provider_unavailable") from None
            if length < 0 or length > MAX_RAW_BODY_BYTES:
                raise WebAccessError("body_too_large")
            return await self._read_exact_bounded(reader, length)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await asyncio.wait_for(reader.read(64 * 1024), timeout=READ_IDLE_TIMEOUT_SECONDS)
            if not chunk:
                return b"".join(chunks)
            total += len(chunk)
            if total > MAX_RAW_BODY_BYTES:
                raise WebAccessError("body_too_large")
            chunks.append(chunk)

    async def _read_exact_bounded(self, reader: asyncio.StreamReader, length: int) -> bytes:
        chunks: list[bytes] = []
        remaining = length
        while remaining:
            chunk = await asyncio.wait_for(reader.read(min(64 * 1024, remaining)), timeout=READ_IDLE_TIMEOUT_SECONDS)
            if not chunk:
                raise WebAccessError("provider_unavailable")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    async def _read_chunked(self, reader: asyncio.StreamReader) -> bytes:
        chunks: list[bytes] = []
        total = 0
        trailer_bytes = 0
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=READ_IDLE_TIMEOUT_SECONDS)
            if not line or len(line) > 128 or not line.endswith(b"\r\n"):
                raise WebAccessError("provider_unavailable")
            try:
                raw_size = line[:-2].split(b";", 1)[0]
                if not raw_size or any(char not in b"0123456789abcdefABCDEF" for char in raw_size):
                    raise ValueError
                size = int(raw_size, 16)
            except ValueError:
                raise WebAccessError("provider_unavailable") from None
            if size < 0 or total + size > MAX_RAW_BODY_BYTES:
                raise WebAccessError("body_too_large")
            if size == 0:
                while True:
                    trailer = await asyncio.wait_for(reader.readline(), timeout=READ_IDLE_TIMEOUT_SECONDS)
                    trailer_bytes += len(trailer)
                    if not trailer or trailer_bytes > MAX_HEADER_BYTES:
                        raise WebAccessError("provider_unavailable")
                    if trailer == b"\r\n":
                        return b"".join(chunks)
            chunk = await self._read_exact_bounded(reader, size)
            delimiter = await asyncio.wait_for(reader.readexactly(2), timeout=READ_IDLE_TIMEOUT_SECONDS)
            if delimiter != b"\r\n":
                raise WebAccessError("provider_unavailable")
            total += size
            chunks.append(chunk)
