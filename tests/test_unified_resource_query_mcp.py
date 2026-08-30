import asyncio
import json
from datetime import UTC, datetime

from mcp import Client

from pdi.query import QueryService
from pdi.resource_query import ResourceQueryService
from pdi_mcp import create_server
from tests.test_pdi_mcp import RecordingRepository


def test_unified_resource_query_mcp_contract_is_compact_and_additive() -> None:
    repository = RecordingRepository()
    query = QueryService(
        repository,
        clock=lambda: datetime(2026, 8, 1, tzinfo=UTC),
    )
    server = create_server(
        query,
        resource_query_service=ResourceQueryService(
            query,
            clock=lambda: datetime(2026, 8, 1, tzinfo=UTC),
        ),
    )

    async def exercise() -> None:
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            result = await client.call_tool(
                "pdi_query_resources",
                {
                    "primary": {
                        "kind": "metadata_text",
                        "query": "CURRENT_CONTEXT",
                    },
                    "filters": {
                        "provider": "immich",
                        "mime_category": "text",
                    },
                    "sort": {
                        "basis": "relevance",
                        "direction": "desc",
                    },
                    "limit": 10,
                },
            )
            invalid_sort = await client.call_tool(
                "pdi_query_resources",
                {
                    "primary": {
                        "kind": "provider_semantic",
                        "query": "summit",
                        "provider": "immich",
                    },
                    "sort": {
                        "basis": "path",
                        "direction": "asc",
                    },
                },
            )
            unsupported_provider = await client.call_tool(
                "pdi_query_resources",
                {
                    "primary": {
                        "kind": "provider_semantic",
                        "query": "summit",
                        "provider": "nextcloud",
                    },
                },
            )

        assert len(tools) == 9
        tool = next(tool for tool in tools if tool.name == "pdi_query_resources")
        description = " ".join((tool.description or "").split())
        assert "choose exactly one primary" in description
        assert "no automatic cross-strategy fallback" in description
        assert "continuable=false" in description
        assert "provider=immich" in description
        assert "distinct time bases" in description

        payload = result.structured_content
        assert payload is not None
        assert payload["ok"] is True
        assert payload["schema"] == "pdi.resource-list.v1"
        assert payload["query_kind"] == "metadata_text"
        assert payload["selection_status"] == "complete"
        assert payload["continuation"] is None
        assert payload["scanned_count"] == 1
        assert payload["resources"] == [{
            "resource_ref": repository.resource_ref,
            "title": "CURRENT_CONTEXT.md",
            "resource_type": "file",
            "mime_type": "text/markdown",
            "mime_category": "text",
            "providers": ["immich"],
            "relevant_time": "2026-07-31T12:00:00+00:00",
            "time_basis": "pdi_first_observed_at",
            "rank": 1,
            "match_basis": "title_prefix",
        }]
        encoded = json.dumps(payload)
        resource_keys = set(payload["resources"][0])
        for forbidden in (
            "sources",
            "observations",
            "location",
            "size_bytes",
            "provider_locator",
            "external_id",
            "metadata",
            "raw",
        ):
            assert forbidden not in resource_keys
            assert f'"{forbidden}"' not in encoded
        assert invalid_sort.structured_content["error"]["code"] == (
            "invalid_resource_query_sort"
        )
        assert unsupported_provider.structured_content["error"]["code"] == (
            "provider_capability_unavailable"
        )

    asyncio.run(exercise())
