import asyncio
import ipaddress
from collections import deque

import pytest

from jarvis.web_access.contract import MAX_RAW_BODY_BYTES, WebAccessError
from jarvis.web_access.http import PinnedHttpClient
from jarvis.web_access.security import PinnedTarget, PublicResolver, parse_public_url


PUBLIC_A = ipaddress.ip_address("93.184.216.34")
PUBLIC_B = ipaddress.ip_address("8.8.8.8")


class StaticResolver(PublicResolver):
    def __init__(self, addresses=(PUBLIC_A,)) -> None:
        self.addresses = addresses
        self.calls: list[str] = []

    async def parse_and_resolve(self, raw_url: str) -> PinnedTarget:
        self.calls.append(raw_url)
        return PinnedTarget(parse_public_url(raw_url), tuple(self.addresses))


class GuardedResolver(StaticResolver):
    async def parse_and_resolve(self, raw_url: str) -> PinnedTarget:
        if len(self.calls):
            return await PublicResolver().parse_and_resolve(raw_url)
        return await super().parse_and_resolve(raw_url)


class FakeWriter:
    def __init__(self, peer: str) -> None:
        self.peer = peer
        self.request = bytearray()
        self.closed = False

    def get_extra_info(self, name: str):
        return (self.peer, 443) if name == "peername" else None

    def write(self, data: bytes) -> None:
        self.request.extend(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class FakeConnector:
    def __init__(self, responses: list[bytes], *, peers: list[str] | None = None) -> None:
        self.responses = deque(responses)
        self.peers = deque(peers or [str(PUBLIC_A)] * len(responses))
        self.calls: list[tuple[str, int, object, str | None]] = []
        self.writers: list[FakeWriter] = []

    async def __call__(self, address: str, port: int, context, server_hostname: str | None):
        self.calls.append((address, port, context, server_hostname))
        reader = asyncio.StreamReader()
        reader.feed_data(self.responses.popleft())
        reader.feed_eof()
        writer = FakeWriter(self.peers.popleft())
        self.writers.append(writer)
        return reader, writer  # type: ignore[return-value]


def response(body: bytes = b"ok", *, status: str = "200 OK", headers: tuple[str, ...] = ("Content-Type: text/plain",)) -> bytes:
    values = [f"HTTP/1.1 {status}", *headers]
    if not any(value.lower().startswith(("content-length:", "transfer-encoding:")) for value in headers):
        values.append(f"Content-Length: {len(body)}")
    return ("\r\n".join(values) + "\r\n\r\n").encode() + body


def test_transport_connects_to_pinned_ip_preserves_sni_host_and_never_resolves_twice() -> None:
    resolver = StaticResolver()
    connector = FakeConnector([response()])
    result = asyncio.run(PinnedHttpClient(resolver=resolver, connector=connector).get("https://example.com/path"))
    assert result.body == b"ok"
    assert resolver.calls == ["https://example.com/path"]
    assert connector.calls[0][0] == str(PUBLIC_A)
    assert connector.calls[0][3] == "example.com"
    assert b"Host: example.com\r\n" in connector.writers[0].request
    assert b"Accept-Encoding: identity\r\n" in connector.writers[0].request


def test_toctou_second_hypothetical_dns_answer_is_never_used() -> None:
    class RebindingResolver(StaticResolver):
        async def parse_and_resolve(self, raw_url: str) -> PinnedTarget:
            self.calls.append(raw_url)
            addresses = (PUBLIC_A,) if len(self.calls) == 1 else (ipaddress.ip_address("127.0.0.1"),)
            return PinnedTarget(parse_public_url(raw_url), addresses)

    resolver = RebindingResolver()
    connector = FakeConnector([response()])
    asyncio.run(PinnedHttpClient(resolver=resolver, connector=connector).get("https://rebind.example/"))
    assert resolver.calls == ["https://rebind.example/"]
    assert [call[0] for call in connector.calls] == [str(PUBLIC_A)]


def test_peer_ip_must_belong_to_validated_pinned_set() -> None:
    connector = FakeConnector([response()], peers=[str(PUBLIC_B)])
    with pytest.raises(WebAccessError) as caught:
        asyncio.run(PinnedHttpClient(resolver=StaticResolver(), connector=connector).get("https://example.com/"))
    assert caught.value.code == "non_public_destination"


def test_public_to_private_redirect_is_revalidated_and_blocked() -> None:
    redirect = response(status="302 Found", headers=("Location: http://127.0.0.1/", "Content-Length: 0"), body=b"")
    connector = FakeConnector([redirect])
    with pytest.raises(WebAccessError) as caught:
        asyncio.run(PinnedHttpClient(resolver=GuardedResolver(), connector=connector).get("https://example.com/"))
    assert caught.value.code == "non_public_destination"


def test_https_to_http_redirect_is_blocked_before_second_connection() -> None:
    redirect = response(status="302 Found", headers=("Location: http://example.net/", "Content-Length: 0"), body=b"")
    connector = FakeConnector([redirect])
    resolver = StaticResolver()
    with pytest.raises(WebAccessError) as caught:
        asyncio.run(PinnedHttpClient(resolver=resolver, connector=connector).get("https://example.com/"))
    assert caught.value.code == "redirect_blocked"
    assert len(connector.calls) == 1


def test_authorization_is_never_forwarded_across_redirect_origins() -> None:
    redirect = response(
        status="302 Found",
        headers=("Location: https://other.example/", "Content-Length: 0"),
        body=b"",
    )
    connector = FakeConnector([redirect])
    with pytest.raises(WebAccessError) as caught:
        asyncio.run(
            PinnedHttpClient(resolver=StaticResolver(), connector=connector).request(
                "POST",
                "https://search.example/",
                headers={"authorization": "Bearer secret"},
                body=b"{}",
            )
        )
    assert caught.value.code == "redirect_blocked"
    assert len(connector.calls) == 1
    assert b"Authorization: Bearer secret\r\n" in connector.writers[0].request


def test_redirect_limit_is_exactly_three() -> None:
    redirects = [response(status="302 Found", headers=(f"Location: https://example.com/{index + 1}", "Content-Length: 0"), body=b"") for index in range(4)]
    connector = FakeConnector(redirects)
    with pytest.raises(WebAccessError) as caught:
        asyncio.run(PinnedHttpClient(resolver=StaticResolver(), connector=connector).get("https://example.com/0"))
    assert caught.value.code == "too_many_redirects"
    assert len(connector.calls) == 4


@pytest.mark.parametrize("encoding", ["gzip", "br", "deflate"])
def test_non_identity_content_encoding_is_rejected(encoding: str) -> None:
    connector = FakeConnector([response(headers=("Content-Type: text/plain", f"Content-Encoding: {encoding}"))])
    with pytest.raises(WebAccessError) as caught:
        asyncio.run(PinnedHttpClient(resolver=StaticResolver(), connector=connector).get("https://example.com/"))
    assert caught.value.code == "unsupported_content_encoding"


def test_oversized_content_length_is_rejected_before_body_read() -> None:
    connector = FakeConnector([response(b"", headers=("Content-Type: text/plain", f"Content-Length: {MAX_RAW_BODY_BYTES + 1}"))])
    with pytest.raises(WebAccessError) as caught:
        asyncio.run(PinnedHttpClient(resolver=StaticResolver(), connector=connector).get("https://example.com/"))
    assert caught.value.code == "body_too_large"


def test_chunked_body_is_streamed_and_bound() -> None:
    raw = response(
        b"4\r\ntest\r\n3\r\ning\r\n0\r\n\r\n",
        headers=("Content-Type: text/plain", "Transfer-Encoding: chunked"),
    )
    result = asyncio.run(PinnedHttpClient(resolver=StaticResolver(), connector=FakeConnector([raw])).get("https://example.com/"))
    assert result.body == b"testing"


def test_status_failures_are_sanitized_without_upstream_body() -> None:
    connector = FakeConnector([response(b"private challenge", status="403 Forbidden")])
    with pytest.raises(WebAccessError) as caught:
        asyncio.run(PinnedHttpClient(resolver=StaticResolver(), connector=connector).get("https://example.com/"))
    assert caught.value.code == "http_403"
    assert "private" not in str(caught.value)
