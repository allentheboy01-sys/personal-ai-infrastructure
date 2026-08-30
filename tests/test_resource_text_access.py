import asyncio
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from pdi.query import format_resource_ref
from pdi.resource_access import (
    AmbiguousTextContentError,
    ContentChangedSinceSyncError,
    DEFAULT_TEXT_WINDOW_BYTES,
    InvalidResourceReferenceError,
    InvalidTextContentError,
    InvalidTextWindowError,
    MAX_TEXT_SOURCE_BYTES,
    MAX_TEXT_WINDOW_BYTES,
    NextcloudTextAdapter,
    ProviderInvalidResponseError,
    ProviderTextContent,
    ProviderUnavailableError,
    ResourceAccessUnavailableError,
    ResourceTextService,
    TextResourceAccessSource,
    TextTooLargeError,
    TextUnavailableError,
)


FIXTURE = Path(__file__).parent / "fixtures" / "resource_text_benchmark_b.json"
_UNSET = object()


def _source(
    content: bytes,
    *,
    source_id: str = "source-a",
    locator: str = "documents/notes.md",
    mime_type: str | None = "text/markdown",
    size_bytes: int | None | object = _UNSET,
    digest: str | None = None,
    provider: str = "nextcloud",
    resource_type: str = "file",
) -> TextResourceAccessSource:
    return TextResourceAccessSource(
        source_id=source_id,
        provider=provider,
        provider_locator=locator,
        resource_type=resource_type,
        mime_type=mime_type,
        size_bytes=len(content) if size_bytes is _UNSET else size_bytes,
        blob_sha256=digest or sha256(content).hexdigest(),
        version_tag='"etag"',
    )


class StubRepository:
    def __init__(self, sources=()) -> None:
        self.sources = sources
        self.calls: list[str] = []

    def resolve_text_access_sources(self, asset_id: str):
        self.calls.append(asset_id)
        return self.sources


class StubTextAdapter:
    provider = "nextcloud"

    def __init__(
        self,
        *,
        status_code: int = 200,
        media_type: str | None = "text/markdown",
        content_length: str | None = None,
        content_encoding: str | None = None,
        chunks: tuple[bytes, ...] = (b"text",),
        error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.media_type = media_type
        self.content_length = content_length
        self.content_encoding = content_encoding
        self.chunks = chunks
        self.error = error
        self.calls: list[str] = []
        self.close_count = 0
        self.read_count = 0

    async def open_text(self, locator: str) -> ProviderTextContent:
        self.calls.append(locator)
        if self.error is not None:
            raise self.error

        async def body():
            for chunk in self.chunks:
                self.read_count += 1
                yield chunk

        async def close():
            self.close_count += 1

        return ProviderTextContent(
            status_code=self.status_code,
            media_type=self.media_type,
            content_length=self.content_length,
            body=body(),
            close=close,
            content_encoding=self.content_encoding,
        )


def _service(content: bytes, **source_overrides):
    source = _source(content, **source_overrides)
    adapter = StubTextAdapter(
        media_type=source.mime_type,
        content_length=str(len(content)),
        chunks=(content,),
    )
    service = ResourceTextService(
        StubRepository((source,)),
        {adapter.provider: adapter},
    )
    return service, adapter, source


def _read(service: ResourceTextService, **arguments):
    return asyncio.run(service.read_text(
        format_resource_ref(uuid4()),
        **arguments,
    ))


@pytest.mark.parametrize(
    "media_type",
    [
        "text/markdown",
        "text/plain",
        "text/csv",
        "text/x-python",
        "application/json",
        "application/markdown",
    ],
)
def test_reads_supported_complete_text_without_observation_dependency(
    media_type,
) -> None:
    content = b"complete provider body"
    service, adapter, _ = _service(content, mime_type=media_type)
    result = _read(service)

    assert result.schema == "pdi.resource-text.v1"
    assert result.provider == "nextcloud"
    assert result.media_type == media_type
    assert result.text == "complete provider body"
    assert result.source == "provider_access"
    assert result.content_sha256 == sha256(content).hexdigest()
    assert adapter.calls == ["documents/notes.md"]
    assert adapter.close_count == 1


def test_existing_truncated_excerpt_is_never_used_as_full_text() -> None:
    provider_body = b"complete provider body beyond an old excerpt"
    source = _source(provider_body)
    repository = StubRepository((source,))
    repository.document_text_excerpt = "old truncated excerpt"
    adapter = StubTextAdapter(
        media_type="text/markdown",
        content_length=str(len(provider_body)),
        chunks=(provider_body,),
    )
    result = _read(ResourceTextService(
        repository,
        {adapter.provider: adapter},
    ))

    assert result.text == provider_body.decode()
    assert repository.document_text_excerpt not in result.text


def test_empty_complete_text_is_a_valid_terminal_window() -> None:
    service, adapter, _ = _service(b"")
    result = _read(service)

    assert result.text == ""
    assert result.returned_bytes == 0
    assert result.total_bytes == 0
    assert result.truncated is False
    assert result.next_offset is None
    assert adapter.read_count == 1


def test_text_fidelity_preserves_provider_line_endings() -> None:
    content = b"one\r\ntwo\rthree\n"
    service, _, _ = _service(content, mime_type="text/plain")

    assert _read(service).text == "one\r\ntwo\rthree\n"


def test_benchmark_b_is_one_verified_provider_read() -> None:
    fixture = json.loads(FIXTURE.read_text())
    content = fixture["text"].encode("utf-8")
    expected = fixture["expected"]
    assert len(content) == expected["source_bytes"]
    service, adapter, _ = _service(
        content,
        mime_type=fixture["media_type"],
    )

    result = _read(service)

    assert len(adapter.calls) == expected["provider_read_calls"]
    assert result.returned_bytes == expected["returned_bytes"]
    assert result.total_bytes == expected["total_bytes"]
    assert result.content_sha256 == sha256(content).hexdigest()
    assert expected["content_hash_verified"] is True
    assert expected["mcp_calls"] == 1


def test_changed_provider_bytes_fail_closed_after_complete_hash() -> None:
    expected = b"synchronized body"
    changed = b"provider changed"
    source = _source(expected, size_bytes=len(changed))
    adapter = StubTextAdapter(
        media_type="text/markdown",
        content_length=str(len(changed)),
        chunks=(changed,),
    )
    service = ResourceTextService(
        StubRepository((source,)),
        {adapter.provider: adapter},
    )

    with pytest.raises(ContentChangedSinceSyncError) as captured:
        _read(service)

    assert captured.value.code == "content_changed_since_sync"
    assert adapter.read_count == 1
    assert adapter.close_count == 1


def test_same_hash_sources_select_smallest_source_id_deterministically() -> None:
    content = b"same"
    sources = (
        _source(content, source_id="source-z", locator="z/same.txt"),
        _source(content, source_id="source-a", locator="a/same.txt"),
    )
    adapter = StubTextAdapter(
        media_type="text/markdown",
        content_length="4",
        chunks=(content,),
    )
    result = _read(ResourceTextService(
        StubRepository(sources),
        {adapter.provider: adapter},
    ))

    assert result.text == "same"
    assert adapter.calls == ["a/same.txt"]


def test_different_active_hashes_fail_closed_before_provider_read() -> None:
    first = _source(b"first", source_id="source-a")
    second = _source(b"second", source_id="source-b")
    adapter = StubTextAdapter()
    service = ResourceTextService(
        StubRepository((first, second)),
        {adapter.provider: adapter},
    )

    with pytest.raises(AmbiguousTextContentError):
        _read(service)

    assert adapter.calls == []


def test_invalid_blob_identity_and_unconfigured_provider_are_sanitized() -> None:
    invalid = _source(b"text", digest="not-a-sha256")
    service = ResourceTextService(StubRepository((invalid,)), {})
    with pytest.raises(ResourceAccessUnavailableError):
        _read(service)

    valid = _source(b"text")
    service = ResourceTextService(StubRepository((valid,)), {})
    with pytest.raises(ResourceAccessUnavailableError) as captured:
        _read(service)
    assert "credential" not in str(captured.value).lower()


def test_known_oversize_fails_before_network_read() -> None:
    source = _source(b"small", size_bytes=MAX_TEXT_SOURCE_BYTES + 1)
    adapter = StubTextAdapter()
    service = ResourceTextService(
        StubRepository((source,)),
        {adapter.provider: adapter},
    )

    with pytest.raises(TextTooLargeError):
        _read(service)
    assert adapter.calls == []


def test_unknown_size_stream_stops_at_bound_plus_one() -> None:
    accepted = b"a" * MAX_TEXT_SOURCE_BYTES
    source = _source(
        accepted,
        size_bytes=None,
    )
    adapter = StubTextAdapter(
        media_type="text/markdown",
        content_length=None,
        chunks=(accepted, b"overflow-and-unread-tail"),
    )
    service = ResourceTextService(
        StubRepository((source,)),
        {adapter.provider: adapter},
    )

    with pytest.raises(TextTooLargeError):
        _read(service)
    assert adapter.read_count == 2
    assert adapter.close_count == 1


@pytest.mark.parametrize(
    "content",
    [
        b"invalid-utf8-\xff",
        b"binary\x00content",
        b"binary\x01content",
        "binary\u0085content".encode(),
    ],
)
def test_invalid_utf8_and_binary_controls_fail(content) -> None:
    service, _, _ = _service(content)
    with pytest.raises(InvalidTextContentError):
        _read(service)


def test_utf8_bom_is_removed_and_offsets_use_canonical_representation() -> None:
    raw = b"\xef\xbb\xbfhello"
    service, _, _ = _service(raw)
    result = _read(service)

    assert result.text == "hello"
    assert result.total_bytes == 5
    assert result.content_sha256 == sha256(raw).hexdigest()


def test_multibyte_windows_progress_without_splitting_codepoints() -> None:
    content = "甲乙丙丁".encode()
    service, adapter, _ = _service(content)
    resource_ref = format_resource_ref(uuid4())

    async def run():
        first = await service.read_text(
            resource_ref,
            max_bytes=4,
        )
        second = await service.read_text(
            resource_ref,
            offset_bytes=first.next_offset,
            max_bytes=4,
        )
        terminal = await service.read_text(
            resource_ref,
            offset_bytes=len(content),
            max_bytes=4,
        )
        return first, second, terminal

    first, second, terminal = asyncio.run(run())
    assert first.text == "甲"
    assert first.returned_bytes == 3
    assert first.next_offset == 3
    assert second.text == "乙"
    assert second.next_offset == 6
    assert terminal.text == ""
    assert terminal.returned_bytes == 0
    assert terminal.next_offset is None
    assert len(adapter.calls) == 3


def test_invalid_offset_and_window_bounds_fail_closed() -> None:
    content = "中文".encode()
    service, _, _ = _service(content)
    for arguments in (
        {"offset_bytes": -1},
        {"offset_bytes": 1},
        {"offset_bytes": len(content) + 1},
        {"max_bytes": 3},
        {"max_bytes": MAX_TEXT_WINDOW_BYTES + 1},
        {"max_bytes": True},
    ):
        with pytest.raises(InvalidTextWindowError):
            _read(service, **arguments)

    assert DEFAULT_TEXT_WINDOW_BYTES == 8192
    assert MAX_TEXT_WINDOW_BYTES == 16384


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (302, ProviderInvalidResponseError),
        (404, TextUnavailableError),
        (410, TextUnavailableError),
        (412, ContentChangedSinceSyncError),
        (500, ProviderUnavailableError),
    ],
)
def test_provider_statuses_are_stable_and_redirects_are_not_followed(
    status,
    expected,
) -> None:
    content = b"text"
    source = _source(content)
    adapter = StubTextAdapter(
        status_code=status,
        media_type="text/markdown",
        content_length="4",
        chunks=(content,),
    )
    service = ResourceTextService(
        StubRepository((source,)),
        {adapter.provider: adapter},
    )
    with pytest.raises(expected):
        _read(service)
    assert adapter.read_count == 0
    assert adapter.close_count == 1


def test_provider_timeout_is_sanitized() -> None:
    content = b"text"
    source = _source(content)
    adapter = StubTextAdapter(
        error=ProviderUnavailableError(
            "Nextcloud text service is unavailable"
        )
    )
    service = ResourceTextService(
        StubRepository((source,)),
        {adapter.provider: adapter},
    )
    with pytest.raises(ProviderUnavailableError) as captured:
        _read(service)
    assert "documents/notes.md" not in str(captured.value)


def test_cancelled_text_read_closes_provider_stream() -> None:
    started = asyncio.Event()
    closed = asyncio.Event()
    source = _source(b"expected")

    class BlockingAdapter:
        provider = "nextcloud"

        async def open_text(self, locator):
            del locator

            async def body():
                started.set()
                await asyncio.Event().wait()
                yield b"unreachable"

            async def close():
                closed.set()

            return ProviderTextContent(
                status_code=200,
                media_type="text/markdown",
                content_length=None,
                body=body(),
                close=close,
            )

    service = ResourceTextService(
        StubRepository((source,)),
        {"nextcloud": BlockingAdapter()},
    )

    async def run():
        task = asyncio.create_task(service.read_text(
            format_resource_ref(uuid4()),
        ))
        await asyncio.wait_for(started.wait(), timeout=0.5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(closed.wait(), timeout=0.5)

    asyncio.run(run())


def test_invalid_content_type_and_length_fail_closed() -> None:
    content = b"text"
    source = _source(content)
    for adapter in (
        StubTextAdapter(
            media_type="application/octet-stream",
            content_length="4",
            chunks=(content,),
        ),
        StubTextAdapter(
            media_type="text/markdown",
            content_length="invalid",
            chunks=(content,),
        ),
        StubTextAdapter(
            media_type="text/markdown",
            content_length="5",
            chunks=(content,),
        ),
        StubTextAdapter(
            media_type="text/markdown",
            content_length="4",
            content_encoding="gzip",
            chunks=(content,),
        ),
    ):
        service = ResourceTextService(
            StubRepository((source,)),
            {adapter.provider: adapter},
        )
        with pytest.raises(ProviderInvalidResponseError):
            _read(service)


@pytest.mark.parametrize(
    "mime_type",
    [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.oasis.opendocument.text",
        "application/octet-stream",
        None,
    ],
)
def test_unsupported_documents_are_text_unavailable_without_extension_fallback(
    mime_type,
) -> None:
    content = b"an excerpt may exist elsewhere"
    source = _source(
        content,
        mime_type=mime_type,
        locator="documents/report.docx",
    )
    adapter = StubTextAdapter()
    service = ResourceTextService(
        StubRepository((source,)),
        {adapter.provider: adapter},
    )
    with pytest.raises(TextUnavailableError):
        _read(service)
    assert adapter.calls == []


def test_models_hide_private_source_state_and_are_immutable() -> None:
    source = _source(
        b"text",
        locator="private/folder/secret.md",
        source_id="private-source-id",
    )
    rendered = repr(source)
    assert "private/folder" not in rendered
    assert "private-source-id" not in rendered
    assert source.blob_sha256 not in rendered
    with pytest.raises(FrozenInstanceError):
        source.provider = "changed"


def test_repository_failure_and_invalid_ref_are_sanitized() -> None:
    class FailingRepository:
        def resolve_text_access_sources(self, asset_id):
            del asset_id
            raise RuntimeError(
                "postgresql://private:password@database/pdi"
            )

    service = ResourceTextService(FailingRepository(), {})
    with pytest.raises(InvalidResourceReferenceError):
        asyncio.run(service.read_text("not-a-resource-ref"))
    with pytest.raises(ResourceAccessUnavailableError) as captured:
        _read(service)
    assert "postgresql" not in str(captured.value)
    assert captured.value.__cause__ is None


def test_nextcloud_adapter_encodes_trusted_path_uses_get_and_no_redirects() -> None:
    request_seen: httpx.Request | None = None

    class TextStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"text"

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_seen
        request_seen = request
        return httpx.Response(
            200,
            headers={
                "content-type": "text/markdown",
                "content-length": "4",
            },
            stream=TextStream(),
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )
    adapter = NextcloudTextAdapter(
        "https://cloud.example/base/",
        "user name",
        "private-password",
        client=client,
    )

    async def run():
        opened = await adapter.open_text("folder/space name.md")
        body = b"".join([chunk async for chunk in opened.body])
        await opened.close()
        await client.aclose()
        return body

    assert asyncio.run(run()) == b"text"
    assert request_seen is not None
    assert request_seen.method == "GET"
    assert request_seen.url.path == (
        "/base/remote.php/dav/files/user name/folder/space name.md"
    )
    assert request_seen.headers["authorization"].startswith("Basic ")
    assert request_seen.headers["accept-encoding"] == "identity"


def test_nextcloud_adapter_does_not_follow_provider_redirect() -> None:
    requests_seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return httpx.Response(
            302,
            headers={"location": "https://other.example/private"},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )
    adapter = NextcloudTextAdapter(
        "https://cloud.example",
        "user",
        "password",
        client=client,
    )

    async def run():
        opened = await adapter.open_text("folder/file.md")
        assert opened.status_code == 302
        await opened.close()
        await client.aclose()

    asyncio.run(run())
    assert len(requests_seen) == 1


def test_nextcloud_adapter_normalizes_transport_timeout() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("private upstream", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = NextcloudTextAdapter(
        "https://cloud.example",
        "user",
        "private-password",
        client=client,
    )

    async def run():
        try:
            with pytest.raises(ProviderUnavailableError) as captured:
                await adapter.open_text("folder/file.md")
            assert "private" not in str(captured.value)
            assert "folder/file.md" not in str(captured.value)
        finally:
            await client.aclose()

    asyncio.run(run())


@pytest.mark.parametrize(
    "locator",
    [
        "https://attacker.example/file",
        "../private",
        "folder/../private",
        "folder\\private",
        "folder/\x00private",
        "",
    ],
)
def test_nextcloud_adapter_rejects_non_provider_relative_paths(locator) -> None:
    adapter = NextcloudTextAdapter(
        "https://cloud.example",
        "user",
        "password",
        client=httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"unreachable")
        )),
    )

    async def run():
        try:
            with pytest.raises(ProviderInvalidResponseError):
                await adapter.open_text(locator)
        finally:
            await adapter._client.aclose()

    asyncio.run(run())
