"""Fail-closed public-Internet URL resolution and address validation."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

from .contract import DNS_TIMEOUT_SECONDS, MAX_URL_CHARS, WebAccessError


_NUMERIC_HOST = re.compile(r"^(?:0[xX][0-9a-fA-F]+|[0-9]+)(?:\.(?:0[xX][0-9a-fA-F]+|[0-9]+))*$")
_INTERNAL_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa", ".lan", ".home", ".corp", ".private", ".ts.net")
_INTERNAL_NAMES = frozenset(
    {
        "localhost",
        "metadata",
        "metadata.google.internal",
        "instance-data",
        "instance-data.ec2.internal",
    }
)


def _normalized_ip(value: str | ipaddress.IPv4Address | ipaddress.IPv6Address):
    address = value if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)) else ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def is_public_address(value: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Use Python's conservative global classification, including mapped IPv4."""

    try:
        address = _normalized_ip(value)
        return bool(
            address.is_global
            and not address.is_multicast
            and not address.is_reserved
            and not address.is_unspecified
            and not address.is_loopback
            and not address.is_link_local
            and not address.is_private
        )
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class ParsedPublicUrl:
    url: str
    scheme: str
    hostname: str
    port: int
    target: str
    host_header: str


@dataclass(frozen=True, slots=True)
class PinnedTarget:
    parsed: ParsedPublicUrl
    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]


def parse_public_url(raw_url: str) -> ParsedPublicUrl:
    if not isinstance(raw_url, str) or not 1 <= len(raw_url) <= MAX_URL_CHARS or raw_url != raw_url.strip():
        raise WebAccessError("blocked_url")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in raw_url):
        raise WebAccessError("blocked_url")
    try:
        split = urlsplit(raw_url)
        port = split.port
    except (ValueError, UnicodeError):
        raise WebAccessError("blocked_url") from None
    scheme = split.scheme.lower()
    if scheme not in {"http", "https"}:
        raise WebAccessError("unsupported_scheme")
    if not split.netloc or split.username is not None or split.password is not None or split.hostname is None:
        raise WebAccessError("blocked_url")
    if split.fragment:
        split = SplitResult(split.scheme, split.netloc, split.path, split.query, "")
    if port is None:
        port = 443 if scheme == "https" else 80
    if (scheme, port) not in {("http", 80), ("https", 443)}:
        raise WebAccessError("unsupported_port")
    hostname = split.hostname.rstrip(".").lower()
    if not hostname or "%" in hostname or hostname in _INTERNAL_NAMES or hostname.endswith(_INTERNAL_SUFFIXES):
        raise WebAccessError("non_public_destination")
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise WebAccessError("blocked_url") from None
    try:
        literal = ipaddress.ip_address(ascii_hostname)
    except ValueError:
        if _NUMERIC_HOST.fullmatch(ascii_hostname):
            raise WebAccessError("non_public_destination") from None
    else:
        canonical = literal.compressed.lower()
        if isinstance(literal, ipaddress.IPv4Address) and canonical != ascii_hostname:
            raise WebAccessError("non_public_destination")
        if not is_public_address(literal):
            raise WebAccessError("non_public_destination")
        ascii_hostname = canonical
    path = split.path or "/"
    if not path.startswith("/"):
        raise WebAccessError("blocked_url")
    netloc = f"[{ascii_hostname}]" if ":" in ascii_hostname else ascii_hostname
    canonical_url = urlunsplit((scheme, netloc, path, split.query, ""))
    host_header = netloc
    target = path + (f"?{split.query}" if split.query else "")
    return ParsedPublicUrl(canonical_url, scheme, ascii_hostname, port, target, host_header)


class PublicResolver:
    """Resolve once, then return the complete validated set for pinning."""

    async def resolve(self, parsed: ParsedPublicUrl) -> PinnedTarget:
        try:
            literal = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            try:
                loop = asyncio.get_running_loop()
                answers = await asyncio.wait_for(
                    loop.getaddrinfo(parsed.hostname, parsed.port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM),
                    timeout=DNS_TIMEOUT_SECONDS,
                )
            except (TimeoutError, OSError, socket.gaierror):
                raise WebAccessError("dns_failure") from None
            addresses = []
            for family, _socktype, _protocol, _canonname, sockaddr in answers:
                if family not in {socket.AF_INET, socket.AF_INET6}:
                    continue
                try:
                    addresses.append(_normalized_ip(sockaddr[0]))
                except ValueError:
                    raise WebAccessError("dns_failure") from None
        else:
            addresses = [_normalized_ip(literal)]
        if not addresses or any(not is_public_address(address) for address in addresses):
            raise WebAccessError("non_public_destination")
        unique = tuple(sorted(set(addresses), key=lambda item: (item.version, int(item))))
        return PinnedTarget(parsed, unique)

    async def parse_and_resolve(self, raw_url: str) -> PinnedTarget:
        return await self.resolve(parse_public_url(raw_url))
