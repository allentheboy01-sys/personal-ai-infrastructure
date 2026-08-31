import asyncio
import base64
import json
from uuid import uuid4

import httpx
import pytest
from mcp import Client
from mcp.types import ImageContent

import pdi.resource_access.runtime as resource_access_runtime
from pdi.query import QueryService, format_resource_ref
from pdi.resource_access import (
    AmbiguousAccessSourceError,
    ImmichRepresentationAdapter,
    InvalidResourceReferenceError,
    PREVIEW_MAX_BYTES,
    ProviderInvalidResponseError,
    ProviderRepresentation,
    ProviderUnavailableError,
    RepresentationTooLargeError,
    RepresentationUnavailableError,
    ResourceAccessService,
    ResourceAccessSource,
    ResourceAccessUnavailableError,
    ResourceNotFoundError,
    ResourceRepresentation,
    ResourceRepresentationDescriptor,
    ResourceRepresentationKind,
)
from pdi_mcp import create_server


class UnusedQueryRepository:
    pass


class StubImageService:
    def __init__(
        self,
        payload: bytes,
        media_type: str,
        *,
        error: Exception | None = None,
    ) -> None:
        self.payload = payload
        self.media_type = media_type
        self.error = error
        self.calls: list[tuple[str, ResourceRepresentationKind]] = []
        self.close_calls = 0

    async def open_representation(
        self,
        resource_ref: str,
        representation_kind: ResourceRepresentationKind,
    ) -> ResourceRepresentation:
        self.calls.append((resource_ref, representation_kind))
        if self.error is not None:
            raise self.error

        async def body():
            midpoint = len(self.payload) // 2
            yield self.payload[:midpoint]
            yield self.payload[midpoint:]

        async def close() -> None:
            self.close_calls += 1

        return ResourceRepresentation(
            descriptor=ResourceRepresentationDescriptor(
                resource_ref=resource_ref,
                representation_kind=ResourceRepresentationKind.PREVIEW,
                media_type=self.media_type,
                content_length=len(self.payload),
                etag='"private-etag-sentinel"',
                last_modified="private-last-modified-sentinel",
                provider="immich",
            ),
            body=body(),
            close=close,
        )


async def call_image_tool(server, resource_ref: str):
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
        result = await client.call_tool(
            "pdi_read_resource_image_preview",
            {"resource_ref": resource_ref},
        )
    return tools, result


@pytest.mark.parametrize("media_type", ["image/jpeg", "image/avif"])
def test_image_preview_returns_one_standard_mcp_image_neutrally(
    media_type: str,
) -> None:
    resource_ref = format_resource_ref(uuid4())
    payload = b"synthetic-preview-pixels\x00\x01"
    service = StubImageService(payload, media_type)
    server = create_server(
        QueryService(UnusedQueryRepository()),
        resource_access_service=service,
    )

    tools, result = asyncio.run(call_image_tool(server, resource_ref))

    tool = next(
        item
        for item in tools
        if item.name == "pdi_read_resource_image_preview"
    )
    assert tool.input_schema["properties"].keys() == {"resource_ref"}
    assert tool.input_schema["required"] == ["resource_ref"]
    assert result.is_error is False
    assert len(result.content) == 1
    image = result.content[0]
    assert isinstance(image, ImageContent)
    assert image.mime_type == media_type
    assert base64.b64decode(image.data, validate=True) == payload
    assert base64.b64encode(payload).decode("ascii") == image.data
    assert result.structured_content == {
        "ok": True,
        "schema": "pdi.resource-image-preview.v1",
        "resource_ref": resource_ref,
        "representation": "image_preview",
        "media_type": media_type,
        "byte_length": len(payload),
    }
    assert service.calls == [
        (resource_ref, ResourceRepresentationKind.PREVIEW)
    ]
    assert service.close_calls == 1

    public = json.dumps(
        result.structured_content,
        ensure_ascii=False,
    )
    for forbidden in (
        "private-etag-sentinel",
        "private-last-modified-sentinel",
        "provider_locator",
        "provider.example.invalid",
        "x-api-key",
        "authorization",
        "source_id",
        "database_id",
        "/etc/pdi",
    ):
        assert forbidden.lower() not in public.lower()


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (
            InvalidResourceReferenceError("Resource reference is invalid"),
            "invalid_resource_ref",
        ),
        (ResourceNotFoundError("Resource was not found"), "resource_not_found"),
        (
            RepresentationUnavailableError("Representation is unavailable"),
            "representation_unavailable",
        ),
        (
            AmbiguousAccessSourceError(
                "Resource has multiple eligible access Sources"
            ),
            "ambiguous_access_source",
        ),
        (
            RepresentationTooLargeError(
                "Representation exceeded its byte limit"
            ),
            "representation_too_large",
        ),
        (
            ProviderUnavailableError(
                "Provider representation service is unavailable"
            ),
            "provider_unavailable",
        ),
        (
            ProviderInvalidResponseError(
                "Provider returned an unexpected status"
            ),
            "provider_invalid_response",
        ),
        (
            ResourceAccessUnavailableError(
                "Resource access persistence is unavailable"
            ),
            "resource_access_unavailable",
        ),
    ],
)
def test_image_preview_domain_failures_are_structured_and_have_no_image(
    error: Exception,
    code: str,
) -> None:
    resource_ref = format_resource_ref(uuid4())
    service = StubImageService(b"unused", "image/jpeg", error=error)
    server = create_server(
        QueryService(UnusedQueryRepository()),
        resource_access_service=service,
    )

    _, result = asyncio.run(call_image_tool(server, resource_ref))

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["ok"] is False
    assert result.structured_content["error"]["code"] == code
    assert all(not isinstance(block, ImageContent) for block in result.content)


def test_image_preview_tool_stays_registered_without_immich_configuration() -> None:
    resource_ref = format_resource_ref(uuid4())
    server = create_server(QueryService(UnusedQueryRepository()))

    tools, result = asyncio.run(call_image_tool(server, resource_ref))

    assert "pdi_read_resource_image_preview" in {
        tool.name for tool in tools
    }
    assert result.is_error is False
    assert result.structured_content == {
        "ok": False,
        "error": {
            "code": "resource_access_unavailable",
            "message": "Resource image preview access is unavailable",
        },
    }
    assert all(not isinstance(block, ImageContent) for block in result.content)


class SourceRepository:
    def __init__(self, mappings) -> None:
        self.mappings = mappings

    def resolve_access_sources(self, asset_id: str):
        return self.mappings.get(asset_id)


def source(locator: str) -> ResourceAccessSource:
    return ResourceAccessSource(
        provider="immich",
        provider_locator=locator,
        resource_type="file",
        mime_type="image/jpeg",
    )


def test_actual_resource_access_preserves_consumer_neutral_avif_mime() -> None:
    asset_id = str(uuid4())
    payload = b"synthetic-avif-preview"
    calls = []
    closed = 0

    class AvifAdapter:
        provider = "immich"

        async def open_representation(self, locator, kind):
            nonlocal closed
            calls.append((locator, kind))

            async def body():
                yield payload

            async def close() -> None:
                nonlocal closed
                closed += 1

            return ProviderRepresentation(
                status_code=200,
                media_type="image/avif",
                content_length=str(len(payload)),
                etag=None,
                last_modified=None,
                body=body(),
                close=close,
            )

    adapter = AvifAdapter()
    service = ResourceAccessService(
        SourceRepository({asset_id: (source(asset_id),)}),
        {adapter.provider: adapter},
    )
    server = create_server(
        QueryService(UnusedQueryRepository()),
        resource_access_service=service,
    )

    result = asyncio.run(
        server.call_tool(
            "pdi_read_resource_image_preview",
            {"resource_ref": format_resource_ref(asset_id)},
        )
    )

    assert result.is_error is False
    assert len(result.content) == 1
    image = result.content[0]
    assert isinstance(image, ImageContent)
    assert image.mime_type == "image/avif"
    assert base64.b64decode(image.data, validate=True) == payload
    assert result.structured_content["media_type"] == "image/avif"
    assert result.structured_content["byte_length"] == len(payload)
    assert calls == [(asset_id, ResourceRepresentationKind.PREVIEW)]
    assert closed == 1


def test_resource_access_oversize_fails_before_any_mcp_image_content() -> None:
    asset_id = str(uuid4())
    closed = 0

    class OversizeAdapter:
        provider = "immich"

        async def open_representation(self, locator, kind):
            assert locator == asset_id
            assert kind is ResourceRepresentationKind.PREVIEW

            async def body():
                raise AssertionError("oversized response body must not be read")
                yield b""

            async def close() -> None:
                nonlocal closed
                closed += 1

            return ProviderRepresentation(
                status_code=200,
                media_type="image/jpeg",
                content_length=str(PREVIEW_MAX_BYTES + 1),
                etag=None,
                last_modified=None,
                body=body(),
                close=close,
            )

    adapter = OversizeAdapter()
    service = ResourceAccessService(
        SourceRepository({asset_id: (source(asset_id),)}),
        {adapter.provider: adapter},
    )
    server = create_server(
        QueryService(UnusedQueryRepository()),
        resource_access_service=service,
    )

    result = asyncio.run(
        server.call_tool(
            "pdi_read_resource_image_preview",
            {"resource_ref": format_resource_ref(asset_id)},
        )
    )

    assert result.structured_content["error"]["code"] == (
        "representation_too_large"
    )
    assert all(not isinstance(block, ImageContent) for block in result.content)
    assert closed == 1


def test_provider_transport_failure_is_sanitized_at_public_mcp_boundary() -> None:
    asset_id = str(uuid4())
    secret_url = "https://private-provider.example.invalid"
    secret_key = "IMMICH_TEST_SECRET_SENTINEL"
    secret_locator = asset_id

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            f"failed {secret_url} locator={secret_locator} key={secret_key}",
            request=request,
        )

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(fail))
        adapter = ImmichRepresentationAdapter(
            secret_url,
            secret_key,
            client=client,
        )
        service = ResourceAccessService(
            SourceRepository({asset_id: (source(asset_id),)}),
            {adapter.provider: adapter},
        )
        server = create_server(
            QueryService(UnusedQueryRepository()),
            resource_access_service=service,
        )
        try:
            result = await server.call_tool(
                "pdi_read_resource_image_preview",
                {"resource_ref": format_resource_ref(asset_id)},
            )
        finally:
            await client.aclose()
        return result

    result = asyncio.run(run())
    assert result.structured_content == {
        "ok": False,
        "error": {
            "code": "provider_unavailable",
            "message": "Immich representation service is unavailable",
        },
    }
    serialized = json.dumps(result.structured_content)
    assert secret_url not in serialized
    assert secret_key not in serialized
    assert secret_locator not in serialized


def test_cancellation_closes_stream_releases_slot_and_returns_no_partial_image() -> None:
    first_id = str(uuid4())
    second_id = str(uuid4())

    class CancellationAdapter:
        provider = "immich"

        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.first_closed = asyncio.Event()
            self.active = 0

        async def open_representation(self, locator, kind):
            assert kind is ResourceRepresentationKind.PREVIEW
            self.active += 1

            async def body():
                if locator == first_id:
                    self.started.set()
                    yield b"partial-image"
                    await asyncio.Event().wait()
                else:
                    yield b"complete-image"

            closed = False

            async def close() -> None:
                nonlocal closed
                if closed:
                    return
                closed = True
                self.active -= 1
                if locator == first_id:
                    self.first_closed.set()

            length = None if locator == first_id else len(b"complete-image")
            return ProviderRepresentation(
                status_code=200,
                media_type="image/jpeg",
                content_length=None if length is None else str(length),
                etag=None,
                last_modified=None,
                body=body(),
                close=close,
            )

    adapter = CancellationAdapter()
    service = ResourceAccessService(
        SourceRepository({
            first_id: (source(first_id),),
            second_id: (source(second_id),),
        }),
        {adapter.provider: adapter},
        max_active_streams=1,
    )
    server = create_server(
        QueryService(UnusedQueryRepository()),
        resource_access_service=service,
    )

    async def run() -> None:
        pending = asyncio.create_task(server.call_tool(
            "pdi_read_resource_image_preview",
            {"resource_ref": format_resource_ref(first_id)},
        ))
        await asyncio.wait_for(adapter.started.wait(), timeout=2)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        await asyncio.wait_for(adapter.first_closed.wait(), timeout=2)
        assert adapter.active == 0

        result = await asyncio.wait_for(
            server.call_tool(
                "pdi_read_resource_image_preview",
                {"resource_ref": format_resource_ref(second_id)},
            ),
            timeout=2,
        )
        assert result.is_error is False
        assert len(result.content) == 1
        image = result.content[0]
        assert isinstance(image, ImageContent)
        assert base64.b64decode(image.data, validate=True) == b"complete-image"
        assert adapter.active == 0

    asyncio.run(run())


def test_mcp_lifespan_closes_owned_resource_access_exactly_once() -> None:
    close_calls = 0

    async def close() -> None:
        nonlocal close_calls
        close_calls += 1

    server = create_server(
        QueryService(UnusedQueryRepository()),
        resource_access_close=close,
    )

    async def run() -> None:
        async with Client(server):
            pass

    asyncio.run(run())
    assert close_calls == 1


def test_shared_immich_runtime_closes_owned_adapter_exactly_once(
    monkeypatch,
) -> None:
    class Adapter:
        provider = "immich"

        def __init__(self, base_url: str, api_key: str) -> None:
            assert base_url == "https://provider.example.invalid"
            assert api_key == "IMMICH_TEST_SECRET_SENTINEL"
            self.close_calls = 0

        async def aclose(self) -> None:
            self.close_calls += 1

    adapter = Adapter(
        "https://provider.example.invalid",
        "IMMICH_TEST_SECRET_SENTINEL",
    )
    monkeypatch.setattr(
        resource_access_runtime,
        "ImmichRepresentationAdapter",
        lambda _base_url, _api_key: adapter,
    )
    runtime = resource_access_runtime.create_immich_resource_access_runtime(
        SourceRepository({}),
        base_url="https://provider.example.invalid",
        api_key="IMMICH_TEST_SECRET_SENTINEL",
    )

    async def close_twice() -> None:
        await runtime.aclose()
        await runtime.aclose()

    asyncio.run(close_twice())
    assert adapter.close_calls == 1
