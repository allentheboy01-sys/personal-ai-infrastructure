import hashlib
import string
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContentEvidence:
    """Digest and exact byte length from one content stream."""

    sha256: str
    byte_length: int

    def __post_init__(self) -> None:
        if (
            type(self.sha256) is not str
            or len(self.sha256) != 64
            or any(character not in string.hexdigits for character in self.sha256)
        ):
            raise ValueError("sha256 must be a 64-character hexadecimal string")

        if type(self.byte_length) is not int or self.byte_length < 0:
            raise ValueError("byte_length must be a non-negative integer")


def calculate_content_evidence(
    chunks: Iterable[bytes | bytearray | memoryview],
) -> ContentEvidence:
    """Calculate content evidence in one streaming pass."""

    digest = hashlib.sha256()
    byte_length = 0

    for chunk in chunks:
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("content chunks must be bytes-like")

        normalized = bytes(chunk)
        digest.update(normalized)
        byte_length += len(normalized)

    return ContentEvidence(
        sha256=digest.hexdigest(),
        byte_length=byte_length,
    )


def calculate_sha256(chunks: Iterable[bytes]) -> str:
    """Return only the digest for backward compatibility."""

    return calculate_content_evidence(chunks).sha256
