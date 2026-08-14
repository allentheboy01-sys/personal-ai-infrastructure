from hashlib import sha256
import json
from uuid import uuid4

import pytest
import requests

from pdi.observation import (
    EnrichmentResource,
    EnrichmentSource,
    EnrichmentWorker,
    MAX_SOURCE_BYTES,
    MAX_STORED_TEXT_BYTES,
    NextcloudContentReader,
    NextcloudTextExtractor,
    ObservationExtractionError,
    TRUNCATION_MARKER,
)
from pdi.observation.nextcloud_text import _truncate_text
from pdi.query import format_resource_ref


class RecordingReader:
    def __init__(
        self,
        content: bytes = b"",
        *,
        chunks: tuple[bytes, ...] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.content = content
        self.chunks = chunks
        self.error = error
        self.sources: list[EnrichmentSource] = []

    def open(self, source: EnrichmentSource):
        self.sources.append(source)
        if self.error is not None:
            raise self.error
        return iter(self.chunks or (self.content,))


def _source(
    content: bytes,
    *,
    source_id: str = "source-a",
    digest: str | None = None,
    size: int | None = None,
    mime_type: str = "text/plain",
    name: str = "notes.txt",
    metadata: dict | None = None,
    provider_locator: str = "private-provider-locator",
) -> EnrichmentSource:
    return EnrichmentSource(
        source_id=source_id,
        provider="nextcloud",
        metadata=metadata or {"href": "/private/content"},
        provider_locator=provider_locator,
        blob_sha256=digest or sha256(content).hexdigest(),
        size=len(content) if size is None else size,
        mime_type=mime_type,
        path=f"folder/{name}",
        name=name,
        version_tag='"etag"',
    )


def _resource(*sources: EnrichmentSource) -> EnrichmentResource:
    return EnrichmentResource(
        format_resource_ref(uuid4()),
        tuple(sources),
    )


def _extract(content: bytes, **source_overrides):
    reader = RecordingReader(content)
    resource = _resource(_source(content, **source_overrides))
    return NextcloudTextExtractor(reader).extract(resource), reader


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"plain ASCII", "plain ASCII"),
        ("Unicode \u4e2d\u6587".encode(), "Unicode \u4e2d\u6587"),
        (b"\xef\xbb\xbfBOM", "BOM"),
        (b"one\r\ntwo\r\n", "one\ntwo\n"),
        (b"one\rtwo\r", "one\ntwo\n"),
        (b"# Heading\n\n- **bold**\n", "# Heading\n\n- **bold**\n"),
    ],
)
def test_extracts_utf8_and_preserves_only_approved_normalization(
    content,
    expected,
) -> None:
    batch, reader = _extract(
        content,
        mime_type="text/markdown",
        name="notes.md",
    )

    assert len(reader.sources) == 1
    assert len(batch.statements) == 1
    statement = batch.statements[0]
    assert statement.predicate == "document.text_excerpt"
    assert statement.value.value == expected
    assert statement.evidence.source_kind == "resource_content"
    assert statement.evidence.source_locator == (
        "nextcloud.webdav.content"
    )
    assert statement.confidence is None


def test_empty_file_completes_with_zero_statements() -> None:
    batch, reader = _extract(b"")

    assert len(reader.sources) == 1
    assert batch.covered_predicates == ("document.text_excerpt",)
    assert batch.statements == ()


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"\xff", "invalid_text_encoding"),
        (b"text\x00data", "binary_content"),
        (b"text\x01data", "binary_content"),
        (b"text\x0bdata", "binary_content"),
        (b"text\x1fdata", "binary_content"),
        (b"text\x7fdata", "binary_content"),
    ],
)
def test_rejects_invalid_encoding_and_binary_controls(
    content,
    code,
) -> None:
    with pytest.raises(ObservationExtractionError) as captured:
        _extract(content)

    assert captured.value.code == code


def test_accepts_source_exactly_at_network_bound() -> None:
    content = b"a" * MAX_SOURCE_BYTES
    batch, reader = _extract(content)

    assert len(reader.sources) == 1
    value = batch.statements[0].value.value
    assert len(value.encode()) == MAX_STORED_TEXT_BYTES
    assert value.endswith(TRUNCATION_MARKER)


@pytest.mark.parametrize("declared_size", [MAX_SOURCE_BYTES + 1, 2**30])
def test_declared_oversize_fails_without_provider_read(
    declared_size,
) -> None:
    content = b"small"
    source = _source(content, size=declared_size)
    reader = RecordingReader(content)

    with pytest.raises(ObservationExtractionError) as captured:
        NextcloudTextExtractor(reader).extract(_resource(source))

    assert captured.value.code == "source_too_large"
    assert reader.sources == []


def test_stream_oversize_consumes_only_bound_plus_one() -> None:
    first = b"a" * MAX_SOURCE_BYTES
    reader = RecordingReader(chunks=(first, b"overflow-and-more"))
    source = _source(
        first,
        size=None,
        digest=sha256(first).hexdigest(),
    )

    with pytest.raises(ObservationExtractionError) as captured:
        NextcloudTextExtractor(reader).extract(_resource(source))

    assert captured.value.code == "source_too_large"
    assert len(reader.sources) == 1


def test_digest_mismatch_fails_without_statement() -> None:
    content = b"provider changed"
    source = _source(content, digest="a" * 64)
    reader = RecordingReader(content)

    with pytest.raises(ObservationExtractionError) as captured:
        NextcloudTextExtractor(reader).extract(_resource(source))

    assert captured.value.code == "content_changed_since_sync"


def test_truncation_exact_boundary_and_marker() -> None:
    exact = "a" * MAX_STORED_TEXT_BYTES
    assert _truncate_text(exact) == exact

    truncated = _truncate_text(exact + "b")
    assert truncated.endswith(TRUNCATION_MARKER)
    assert len(truncated.encode()) == MAX_STORED_TEXT_BYTES


def test_truncation_never_splits_unicode_codepoint() -> None:
    text = "\u4e2d" * MAX_STORED_TEXT_BYTES
    truncated = _truncate_text(text)

    assert truncated.endswith(TRUNCATION_MARKER)
    assert len(truncated.encode("utf-8")) <= MAX_STORED_TEXT_BYTES
    truncated.encode("utf-8").decode("utf-8")


def test_fingerprint_is_stable_private_and_changes_with_blob_or_mime() -> None:
    content = b"fingerprint"
    first = _source(content)
    same_input_other_source = _source(
        content,
        source_id="source-b",
        provider_locator="different-private-locator",
        metadata={"href": "/different/private/path"},
        name="different.txt",
    )
    changed_blob = _source(b"changed")
    changed_mime = _source(content, mime_type="text/markdown")
    extractor = NextcloudTextExtractor(RecordingReader(content))

    fingerprint = extractor.input_fingerprint(_resource(first))
    expected = sha256(json.dumps(
        {
            "format": "pdi.nextcloud_text.input.v1",
            "provider": "nextcloud",
            "blob_sha256": sha256(content).hexdigest(),
            "mime_type": "text/plain",
            "extractor_version": "1",
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()).hexdigest()
    assert fingerprint == expected
    assert fingerprint == extractor.input_fingerprint(
        _resource(same_input_other_source)
    )
    assert fingerprint != extractor.input_fingerprint(
        _resource(changed_blob)
    )
    assert fingerprint != extractor.input_fingerprint(
        _resource(changed_mime)
    )


def test_same_blob_multiple_sources_uses_deterministic_source_once() -> None:
    content = b"same content"
    later = _source(content, source_id="source-z")
    earlier = _source(content, source_id="source-a")
    reader = RecordingReader(content)
    resource = _resource(later, earlier)

    batch = NextcloudTextExtractor(reader).extract(resource)

    assert batch.statements[0].value.value == "same content"
    assert [source.source_id for source in reader.sources] == ["source-a"]


def test_different_blob_sources_fail_ambiguously_without_read() -> None:
    reader = RecordingReader(b"first")
    resource = _resource(
        _source(b"first", source_id="source-a"),
        _source(b"second", source_id="source-b"),
    )

    with pytest.raises(ObservationExtractionError) as captured:
        NextcloudTextExtractor(reader).input_fingerprint(resource)

    assert captured.value.code == "ambiguous_active_nextcloud_content"
    assert reader.sources == []


def test_mark_running_shortcut_skips_provider_read_and_writes() -> None:
    content = b"already complete"
    resource = _resource(_source(content))
    reader = RecordingReader(content)

    class CompletedRepository:
        def __init__(self) -> None:
            self.providers = []
            self.publishes = 0

        def list_enrichment_resources(self, *, provider):
            self.providers.append(provider)
            return (resource,)

        def mark_running(self, *args, **kwargs):
            return False

        def publish(self, *args, **kwargs):
            self.publishes += 1
            raise AssertionError("publish must not be called")

    repository = CompletedRepository()
    result = EnrichmentWorker(
        repository,
        NextcloudTextExtractor(reader),
        provider="nextcloud",
    ).run_once(batch_size=1)

    assert repository.providers == ["nextcloud"]
    assert reader.sources == []
    assert repository.publishes == 0
    assert result.discovered == 1
    assert result.skipped == 1
    assert result.statement_writes == 0


def test_noneligible_resource_is_not_discovered_by_worker() -> None:
    content = b"not eligible"
    source = _source(
        content,
        mime_type="application/pdf",
        name="document.pdf",
    )
    resource = _resource(source)
    reader = RecordingReader(content)

    class Repository:
        def list_enrichment_resources(self, *, provider):
            assert provider == "nextcloud"
            return (resource,)

    result = EnrichmentWorker(
        Repository(),
        NextcloudTextExtractor(reader),
        provider="nextcloud",
    ).run_once(batch_size=1)

    assert result.discovered == 0
    assert reader.sources == []


def test_extension_fallback_is_eligible() -> None:
    content = b"# Markdown"
    source = _source(
        content,
        mime_type="application/octet-stream",
        name="notes.markdown",
    )
    reader = RecordingReader(content)

    batch = NextcloudTextExtractor(reader).extract(_resource(source))

    assert batch.statements[0].value.value == "# Markdown"


def test_content_reader_delegates_to_adapter_with_private_fact() -> None:
    content = b"delegated"

    class Adapter:
        def __init__(self) -> None:
            self.facts = []

        def open(self, fact):
            self.facts.append(fact)
            return iter((content,))

    adapter = Adapter()
    source = _source(content)
    result = b"".join(NextcloudContentReader(adapter).open(source))

    assert result == content
    assert len(adapter.facts) == 1
    fact = adapter.facts[0]
    assert fact.provider == "nextcloud"
    assert fact.kind == "file"
    assert fact.raw == {"href": "/private/content"}


def test_content_reader_sanitizes_provider_failure() -> None:
    class Adapter:
        def open(self, fact):
            raise requests.HTTPError(
                "secret provider URL and credentials"
            )
            yield b""

    source = _source(b"content")
    with pytest.raises(ObservationExtractionError) as captured:
        tuple(NextcloudContentReader(Adapter()).open(source))

    assert captured.value.code == "provider_read_failed"
    assert "secret" not in str(captured.value)
