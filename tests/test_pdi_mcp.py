import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

from mcp import Client

from pdi.query import (
    ContentSummary,
    QueryService,
    ResourceAggregationBucket,
    ResourceAggregationQuery,
    ResourceAggregationResult,
    ResourceDetail,
    ResourceListPageQuery,
    ResourceSearchPageQuery,
    ResourceSourceSummary,
    ResourceSummary,
    format_resource_ref,
    parse_resource_ref,
)
from pdi_mcp import create_server


class RecordingRepository:
    def __init__(self) -> None:
        self.asset_id = str(uuid4())
        self.resource_ref = format_resource_ref(self.asset_id)
        self.source = ResourceSourceSummary(
            provider="immich",
            location="/library/CURRENT_CONTEXT.md",
            name="CURRENT_CONTEXT.md",
            mime_type="text/markdown",
            size_bytes=4096,
            is_active=True,
        )
        self.summary = ResourceSummary(
            resource_ref=self.resource_ref,
            resource_type="file",
            display_name="CURRENT_CONTEXT.md",
            pdi_first_observed_at=datetime(
                2026,
                7,
                31,
                12,
                tzinfo=UTC,
            ),
            sources=(self.source,),
        )
        self.detail = ResourceDetail(
            resource_ref=self.resource_ref,
            resource_type="file",
            display_name="CURRENT_CONTEXT.md",
            pdi_first_observed_at=(
                self.summary.pdi_first_observed_at
            ),
            sources=(self.source,),
            content_variants=(
                ContentSummary(
                    mime_type="text/markdown",
                    size_bytes=4096,
                    checksum="sha256-current-context",
                ),
            ),
        )
        self.recent_query: ResourceListPageQuery | None = None
        self.search_query: ResourceSearchPageQuery | None = None

    def list_resource_page(
        self,
        query: ResourceListPageQuery,
    ) -> tuple[ResourceSummary, ...]:
        self.recent_query = query
        return (self.summary,)

    def search_resource_page(
        self,
        query: ResourceSearchPageQuery,
    ) -> tuple[ResourceSummary, ...]:
        self.search_query = query
        return (self.summary,)

    def aggregate_resources(
        self,
        query: ResourceAggregationQuery,
    ) -> ResourceAggregationResult:
        return ResourceAggregationResult(
            time_basis="pdi_first_observed_at",
            time_range=query.time_range,
            applied_filters=query.filters,
            group_by=query.group_by,
            total_count=1,
            buckets=(
                ()
                if query.group_by is None
                else (ResourceAggregationBucket("immich", 1),)
            ),
            buckets_truncated=False,
        )

    def get_resource_detail(
        self,
        asset_id: str,
    ) -> ResourceDetail | None:
        if asset_id == self.asset_id:
            return self.detail
        return None


def test_mcp_tools_convert_arguments_and_serialize_dtos() -> None:
    repository = RecordingRepository()
    service = QueryService(
        repository,
        clock=lambda: datetime(2026, 7, 31, 12, tzinfo=UTC),
    )
    server = create_server(service)

    async def exercise_tools() -> None:
        async with Client(server) as client:
            recent_result = await client.call_tool(
                "pdi_list_recent_resources",
                {
                    "days": 14,
                    "provider": "immich",
                    "resource_type": "file",
                    "mime_type": "text/markdown",
                    "path_prefix": "/library",
                    "limit": 12,
                },
            )
            search_result = await client.call_tool(
                "pdi_search_resources",
                {
                    "query": "CURRENT_CONTEXT",
                    "provider": "immich",
                    "limit": 8,
                },
            )
            detail_result = await client.call_tool(
                "pdi_get_resource",
                {"resource_ref": repository.resource_ref},
            )

        assert recent_result.is_error is False
        assert recent_result.structured_content is not None
        assert recent_result.structured_content["ok"] is True
        assert recent_result.structured_content["next_cursor"] is None
        resource = recent_result.structured_content["resources"][0]
        assert resource == {
            "resource_ref": repository.resource_ref,
            "resource_type": "file",
            "display_name": "CURRENT_CONTEXT.md",
            "pdi_first_observed_at": "2026-07-31T12:00:00+00:00",
            "sources": [
                {
                    "provider": "immich",
                    "location": "/library/CURRENT_CONTEXT.md",
                    "name": "CURRENT_CONTEXT.md",
                    "mime_type": "text/markdown",
                    "size_bytes": 4096,
                    "is_active": True,
                }
            ],
        }
        assert search_result.structured_content is not None
        assert search_result.structured_content["ok"] is True
        assert search_result.structured_content["next_cursor"] is None
        assert "checksum" not in json.dumps(
            recent_result.structured_content
        )
        assert "checksum" not in json.dumps(
            search_result.structured_content
        )
        assert detail_result.structured_content is not None
        assert detail_result.structured_content["resource"][
            "content_variants"
        ] == [
            {
                "mime_type": "text/markdown",
                "size_bytes": 4096,
                "checksum": "sha256-current-context",
            }
        ]

        encoded_results = json.dumps(
            [
                recent_result.structured_content,
                search_result.structured_content,
                detail_result.structured_content,
            ]
        )
        for internal_name in (
            "asset_id",
            "blob_id",
            "source_id",
            "external_id",
            "metadata",
            "raw",
            "primary_source",
        ):
            assert internal_name not in encoded_results

    asyncio.run(exercise_tools())

    assert repository.recent_query is not None
    assert repository.recent_query.filters.provider == "immich"
    assert repository.recent_query.limit == 13
    assert repository.search_query is not None
    assert repository.search_query.query == "CURRENT_CONTEXT"
    assert repository.search_query.limit == 9


def test_mcp_maps_query_errors_and_distinguishes_not_found() -> None:
    repository = RecordingRepository()
    server = create_server(QueryService(repository))
    missing_ref = format_resource_ref(uuid4())

    async def exercise_errors() -> None:
        async with Client(server) as client:
            invalid_query = await client.call_tool(
                "pdi_list_recent_resources",
                {"days": 0},
            )
            invalid_ref = await client.call_tool(
                "pdi_get_resource",
                {"resource_ref": "pdi:resource:invalid"},
            )
            missing = await client.call_tool(
                "pdi_get_resource",
                {"resource_ref": missing_ref},
            )

        assert invalid_query.structured_content["error"]["code"] == (
            "invalid_query"
        )
        assert invalid_ref.structured_content["error"]["code"] == (
            "invalid_resource_ref"
        )
        assert missing.structured_content["error"]["code"] == (
            "resource_not_found"
        )
        assert parse_resource_ref(missing_ref)

    asyncio.run(exercise_errors())


def test_recent_tool_description_protects_time_semantics() -> None:
    server = create_server(QueryService(RecordingRepository()))

    async def inspect_tools() -> None:
        async with Client(server) as client:
            tools = (await client.list_tools()).tools

        recent_tool = next(
            tool
            for tool in tools
            if tool.name == "pdi_list_recent_resources"
        )
        assert recent_tool.description is not None
        assert (
            "The returned time represents when PDI first created the "
            "resource\nrecord. It does not prove when the user created, "
            "uploaded, modified,\nor completed the resource."
            in recent_tool.description
        )

    asyncio.run(inspect_tools())


def test_mcp_aggregation_is_the_only_new_tool_and_serializes_semantics() -> None:
    repository = RecordingRepository()
    server = create_server(QueryService(repository))

    async def exercise() -> None:
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            grouped = await client.call_tool(
                "pdi_aggregate_resources",
                {
                    "group_by": "provider",
                    "observed_from": "2026-08-01T08:00:00+08:00",
                    "observed_to": "2026-08-02T00:00:00+00:00",
                    "mime_category": "image",
                },
            )
            count_only = await client.call_tool(
                "pdi_aggregate_resources",
                {},
            )
            invalid_time = await client.call_tool(
                "pdi_aggregate_resources",
                {"observed_from": "2026-08-01T00:00:00"},
            )

        assert {tool.name for tool in tools} == {
            "pdi_list_recent_resources",
            "pdi_search_resources",
            "pdi_get_resource",
            "pdi_aggregate_resources",
        }
        payload = grouped.structured_content
        assert payload is not None
        assert payload == {
            "ok": True,
            "time_basis": "pdi_first_observed_at",
            "observed_from": "2026-08-01T00:00:00+00:00",
            "observed_to": "2026-08-02T00:00:00+00:00",
            "applied_filters": {
                "provider": None,
                "resource_type": None,
                "mime_type": None,
                "mime_category": "image",
                "path_prefix": None,
            },
            "group_by": "provider",
            "total_count": 1,
            "buckets": [{"key": "immich", "count": 1}],
            "buckets_truncated": False,
        }
        assert count_only.structured_content["group_by"] is None
        assert count_only.structured_content["buckets"] == []
        assert invalid_time.structured_content["error"]["code"] == (
            "invalid_query"
        )

    asyncio.run(exercise())
