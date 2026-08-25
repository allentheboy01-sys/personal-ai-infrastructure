import asyncio
import ipaddress
import socket

import pytest

from jarvis.web_access.contract import WebAccessError
from jarvis.web_access.security import PublicResolver, parse_public_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://10.1.2.3/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/",
        "http://100.64.0.1/",
        "http://224.0.0.1/",
        "http://192.0.2.1/",
        "http://198.18.0.1/",
        "http://[::ffff:127.0.0.1]/",
        "https://node.tailnet.ts.net/",
        "http://2130706433/",
        "http://0177.0.0.1/",
        "http://0x7f.0.0.1/",
    ],
)
def test_literal_and_internal_destinations_fail_closed(url: str) -> None:
    with pytest.raises(WebAccessError) as caught:
        parse_public_url(url)
    assert caught.value.code == "non_public_destination"


@pytest.mark.parametrize("url", ["example.com", "file:///etc/passwd", "ftp://example.com/x", "data:text/plain,x", "ws://example.com/"])
def test_scheme_allowlist(url: str) -> None:
    with pytest.raises(WebAccessError) as caught:
        parse_public_url(url)
    assert caught.value.code == "unsupported_scheme"


@pytest.mark.parametrize("url", ["https://user@example.com/", "https://user:pass@example.com/", "https://example.com:8443/", "http://example.com:443/"])
def test_userinfo_and_unsupported_ports_are_rejected(url: str) -> None:
    with pytest.raises(WebAccessError) as caught:
        parse_public_url(url)
    assert caught.value.code in {"blocked_url", "unsupported_port"}


def test_canonical_url_removes_fragment_default_port_and_trailing_dot() -> None:
    value = parse_public_url("HTTPS://Example.COM.:443/a?q=1#fragment")
    assert value.url == "https://example.com/a?q=1"
    assert value.host_header == "example.com"
    assert value.target == "/a?q=1"


def test_dns_mixed_public_and_private_answers_rejects_entire_hostname() -> None:
    async def run() -> None:
        parsed = parse_public_url("https://example.com/")
        loop = asyncio.get_running_loop()
        original = loop.getaddrinfo

        async def fake(*_args, **_kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443)),
            ]

        loop.getaddrinfo = fake  # type: ignore[method-assign]
        try:
            with pytest.raises(WebAccessError) as caught:
                await PublicResolver().resolve(parsed)
            assert caught.value.code == "non_public_destination"
        finally:
            loop.getaddrinfo = original  # type: ignore[method-assign]

    asyncio.run(run())


def test_all_dns_answers_are_collected_deduplicated_and_sorted() -> None:
    async def run() -> None:
        parsed = parse_public_url("https://example.com/")
        loop = asyncio.get_running_loop()
        original = loop.getaddrinfo

        async def fake(*_args, **_kwargs):
            return [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", 443, 0, 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            ]

        loop.getaddrinfo = fake  # type: ignore[method-assign]
        try:
            pinned = await PublicResolver().resolve(parsed)
            assert pinned.addresses == (ipaddress.ip_address("8.8.8.8"), ipaddress.ip_address("2606:4700:4700::1111"))
        finally:
            loop.getaddrinfo = original  # type: ignore[method-assign]

    asyncio.run(run())
