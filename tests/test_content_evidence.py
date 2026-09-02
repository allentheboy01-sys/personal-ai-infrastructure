import hashlib

import pytest

from pdi.capability.hash import (
    ContentEvidence,
    calculate_content_evidence,
    calculate_sha256,
)


def test_content_evidence_matches_legacy_digest_and_counts_bytes() -> None:
    chunks = [b"alpha", bytearray(b"-beta"), memoryview(b"-gamma")]

    evidence = calculate_content_evidence(chunks)

    expected = b"alpha-beta-gamma"
    assert evidence == ContentEvidence(
        sha256=hashlib.sha256(expected).hexdigest(),
        byte_length=len(expected),
    )
    assert calculate_sha256([expected]) == evidence.sha256


def test_empty_content_evidence() -> None:
    evidence = calculate_content_evidence([])

    assert evidence.sha256 == hashlib.sha256(b"").hexdigest()
    assert evidence.byte_length == 0


def test_content_evidence_is_independent_of_chunking() -> None:
    content = bytes(range(256)) * 32_768
    one_chunk = calculate_content_evidence([content])
    many_chunks = calculate_content_evidence(
        content[offset : offset + 8191]
        for offset in range(0, len(content), 8191)
    )

    assert many_chunks == one_chunk
    assert many_chunks.byte_length == len(content)


def test_content_evidence_supports_noncontiguous_memoryview() -> None:
    view = memoryview(b"abcdef")[::2]

    evidence = calculate_content_evidence([view])

    assert evidence == ContentEvidence(
        sha256=hashlib.sha256(b"ace").hexdigest(),
        byte_length=3,
    )


def test_content_evidence_consumes_iterable_once() -> None:
    class SinglePassChunks:
        def __init__(self) -> None:
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            if self.iterations > 1:
                raise AssertionError("chunks iterable was consumed twice")
            yield b"first"
            yield bytearray(b"second")
            yield memoryview(b"third")

    chunks = SinglePassChunks()

    evidence = calculate_content_evidence(chunks)

    assert chunks.iterations == 1
    assert evidence.byte_length == len(b"firstsecondthird")


@pytest.mark.parametrize("byte_length", [True, -1])
def test_content_evidence_rejects_invalid_byte_length(
    byte_length: object,
) -> None:
    with pytest.raises(ValueError, match="byte_length"):
        ContentEvidence(
            sha256=hashlib.sha256(b"").hexdigest(),
            byte_length=byte_length,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("sha256", [None, "not-a-sha256", "g" * 64])
def test_content_evidence_rejects_invalid_sha256(sha256: object) -> None:
    with pytest.raises(ValueError, match="sha256"):
        ContentEvidence(
            sha256=sha256,  # type: ignore[arg-type]
            byte_length=0,
        )


def test_content_evidence_rejects_non_bytes_chunks() -> None:
    with pytest.raises(TypeError, match="content chunks must be bytes-like"):
        calculate_content_evidence([b"valid", "invalid"])  # type: ignore[list-item]
