import asyncio
from hashlib import sha256
import json
from uuid import uuid4

from mcp import Client

from pdi.query import QueryService, format_resource_ref
from pdi.resource_access import (
    ContentChangedSinceSyncError,
    ResourceText,
)
from pdi_mcp import create_server


class UnusedQueryRepository:
    pass


class StubTextService:
    def __init__(self, *, error=None) -> None:
        self.error = error
        self.calls = []

    async def read_text(
        self,
        resource_ref,
        *,
        offset_bytes,
        max_bytes,
    ):
        self.calls.append({
            "resource_ref": resource_ref,
            "offset_bytes": offset_bytes,
            "max_bytes": max_bytes,
        })
        if self.error is not None:
            raise self.error
        raw = "# Notes\n\n中文\n".encode()
        return ResourceText(
            schema="pdi.resource-text.v1",
            resource_ref=resource_ref,
            provider="nextcloud",
            media_type="text/markdown",
            encoding="utf-8",
            source="provider_access",
            text="# Notes\n\n中文\n",
            offset_bytes=offset_bytes,
            returned_bytes=len(raw),
            total_bytes=len(raw),
            truncated=False,
            next_offset=None,
            content_sha256=sha256(raw).hexdigest(),
        )


def test_mcp_text_tool_has_structured_bounded_contract() -> None:
    resource_ref = format_resource_ref(uuid4())
    service = StubTextService()
    server = create_server(
        QueryService(UnusedQueryRepository()),
        resource_text_service=service,
    )

    async def run():
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            result = await client.call_tool(
                "pdi_read_resource_text",
                {
                    "resource_ref": resource_ref,
                    "offset_bytes": 0,
                    "max_bytes": 8192,
                },
            )
        return tools, result

    tools, result = asyncio.run(run())
    tool = next(tool for tool in tools if tool.name == "pdi_read_resource_text")
    description = " ".join((tool.description or "").split())
    assert "document.text_excerpt" in description
    assert "does not automatically read another window" in description
    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content == {
        "ok": True,
        "schema": "pdi.resource-text.v1",
        "resource_ref": resource_ref,
        "provider": "nextcloud",
        "media_type": "text/markdown",
        "encoding": "utf-8",
        "source": "provider_access",
        "text": "# Notes\n\n中文\n",
        "offset_bytes": 0,
        "returned_bytes": 16,
        "total_bytes": 16,
        "truncated": False,
        "next_offset": None,
        "content_sha256": sha256("# Notes\n\n中文\n".encode()).hexdigest(),
    }
    assert service.calls == [{
        "resource_ref": resource_ref,
        "offset_bytes": 0,
        "max_bytes": 8192,
    }]
    encoded = json.dumps(result.structured_content)
    for forbidden in (
        "provider_locator",
        "webdav",
        "base_url",
        "username",
        "password",
        "source_id",
        "database",
    ):
        assert forbidden not in encoded.lower()


def test_mcp_text_tool_stays_registered_without_provider_configuration() -> None:
    resource_ref = format_resource_ref(uuid4())
    server = create_server(QueryService(UnusedQueryRepository()))

    async def run():
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            result = await client.call_tool(
                "pdi_read_resource_text",
                {"resource_ref": resource_ref},
            )
        return tools, result

    tools, result = asyncio.run(run())
    assert "pdi_read_resource_text" in {tool.name for tool in tools}
    assert result.is_error is False
    assert result.structured_content == {
        "ok": False,
        "error": {
            "code": "resource_access_unavailable",
            "message": "Resource text access is unavailable",
        },
    }


def test_mcp_text_error_is_stable_and_sanitized() -> None:
    resource_ref = format_resource_ref(uuid4())
    service = StubTextService(error=ContentChangedSinceSyncError(
        "Provider content changed since PDI synchronization"
    ))
    server = create_server(
        QueryService(UnusedQueryRepository()),
        resource_text_service=service,
    )

    async def run():
        async with Client(server) as client:
            return await client.call_tool(
                "pdi_read_resource_text",
                {"resource_ref": resource_ref},
            )

    result = asyncio.run(run())
    assert result.is_error is False
    assert result.structured_content == {
        "ok": False,
        "error": {
            "code": "content_changed_since_sync",
            "message": "Provider content changed since PDI synchronization",
        },
    }
