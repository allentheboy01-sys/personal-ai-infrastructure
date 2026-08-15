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
from pdi_mcp.serialization import serialize_rich_retrieval_result
from pdi.observation import (
    Evidence,
    EvidenceSourceKind,
    GeneratorIdentity,
    ObservationService,
    StatementValueType,
    StatementView,
)
from pdi.retrieval import (
    ResourceRetrievalHit,
    ResourceRetrievalResult,
)
from pdi.rich_retrieval import (
    RetrievalStage,
    RichRetrievalHit,
    RichRetrievalResult,
)


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


class RecordingObservationRepository:
    def __init__(self, resource_ref: str) -> None:
        self.resource_ref = resource_ref
        self.predicate = None

    def get_resource_statements(
        self,
        resource_ref,
        *,
        predicate,
        include_history,
        limit,
    ):
        self.predicate = predicate
        assert include_history is False
        assert limit == 100
        if resource_ref != self.resource_ref:
            return None
        return (
            StatementView(
                subject_resource_ref=resource_ref,
                predicate="media.captured_at",
                value_type=StatementValueType.DATETIME,
                value=datetime(2020, 1, 1, tzinfo=UTC),
                generator=GeneratorIdentity(
                    "deterministic_extractor",
                    "immich_metadata",
                    "1",
                ),
                evidence=Evidence(
                    EvidenceSourceKind.PROVIDER_METADATA,
                    "asset_source.metadata.exif.dateTimeOriginal",
                ),
                confidence=None,
                created_at=datetime(2026, 8, 13, tzinfo=UTC),
                is_current=True,
            ),
        )


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


def test_search_and_retrieval_descriptions_define_distinct_intent() -> None:
    server = create_server(QueryService(RecordingRepository()))

    async def inspect_tools() -> None:
        async with Client(server) as client:
            tools = (await client.list_tools()).tools

        descriptions = {
            tool.name: tool.description or ""
            for tool in tools
        }
        search = descriptions["pdi_search_resources"]
        retrieval = descriptions["pdi_retrieve_resources"]
        rich = " ".join(
            descriptions["pdi_rich_retrieve_resources"].split()
        )
        assert "filename, title, source path, metadata" in search
        assert "automatic fallback" in search
        assert "resource content or visual concepts" in retrieval
        assert "do not automatically follow it" in retrieval
        assert "one content candidate source" in rich
        assert "without first calling pdi_retrieve_resources" in rich
        assert "set mime_category to image" in rich
        assert "literal current OCR or document-excerpt" in rich
        assert "does not merge candidate sources" in rich
        assert "do not call observations per hit" in rich
        assert "exactly that one filtered call" in rich
        assert "do not make an unfiltered comparison call" in rich
        assert "require media.captured_at" in rich
        assert "small selected" in rich

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
            "pdi_get_resource_observations",
            "pdi_retrieve_resources",
            "pdi_rich_retrieve_resources",
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


def test_observation_tool_is_the_only_v0_1_addition_and_does_not_leak_ids() -> None:
    query_repository = RecordingRepository()
    observation_repository = RecordingObservationRepository(
        query_repository.resource_ref
    )
    server = create_server(
        QueryService(query_repository),
        ObservationService(observation_repository),
    )

    async def exercise() -> None:
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            result = await client.call_tool(
                "pdi_get_resource_observations",
                {
                    "resource_ref": query_repository.resource_ref,
                    "predicate": "media.captured_at",
                },
            )
            invalid = await client.call_tool(
                "pdi_get_resource_observations",
                {
                    "resource_ref": query_repository.resource_ref,
                    "predicate": "unknown.predicate",
                },
            )

        assert len(tools) == 7
        assert result.structured_content == {
            "ok": True,
            "observations": [{
                "subject_resource_ref": query_repository.resource_ref,
                "predicate": "media.captured_at",
                "value_type": "datetime",
                "value": "2020-01-01T00:00:00+00:00",
                "generator_type": "deterministic_extractor",
                "generator_name": "immich_metadata",
                "generator_version": "1",
                "source_kind": "provider_metadata",
                "source_locator": (
                    "asset_source.metadata.exif.dateTimeOriginal"
                ),
                "confidence": None,
                "created_at": "2026-08-13T00:00:00+00:00",
            }],
        }
        assert invalid.structured_content["error"]["code"] == (
            "invalid_observation"
        )
        observation = result.structured_content["observations"][0]
        for internal in (
            "asset_id", "statement_id", "blob_id", "source_id",
            "external_id", "metadata", "raw",
        ):
            assert internal not in observation

    asyncio.run(exercise())
    assert observation_repository.predicate == "media.captured_at"


def test_retrieval_tool_serializes_public_resources_without_leakage() -> None:
    query_repository = RecordingRepository()

    class RecordingRetrievalService:
        def __init__(self) -> None:
            self.call = None

        def retrieve_resources(self, *, query, provider, limit):
            self.call = (query, provider, limit)
            return ResourceRetrievalResult(
                hits=(ResourceRetrievalHit(
                    resource=query_repository.summary,
                    rank=2,
                    provider="immich",
                    retrieval_kind="semantic",
                ),),
                provider="immich",
                retrieval_kind="semantic",
                unmapped_hit_count=1,
            )

    retrieval_service = RecordingRetrievalService()
    server = create_server(
        QueryService(query_repository),
        retrieval_service=retrieval_service,
    )

    async def exercise() -> None:
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            result = await client.call_tool(
                "pdi_retrieve_resources",
                {
                    "query": "seaside",
                    "provider": "immich",
                    "limit": 4,
                },
            )

        assert len(tools) == 7
        assert result.structured_content == {
            "ok": True,
            "provider": "immich",
            "retrieval_kind": "semantic",
            "hits": [{
                "rank": 2,
                "provider": "immich",
                "retrieval_kind": "semantic",
                "resource": {
                    "resource_ref": query_repository.resource_ref,
                    "resource_type": "file",
                    "display_name": "CURRENT_CONTEXT.md",
                    "pdi_first_observed_at": (
                        "2026-07-31T12:00:00+00:00"
                    ),
                    "sources": [{
                        "provider": "immich",
                        "location": "/library/CURRENT_CONTEXT.md",
                        "name": "CURRENT_CONTEXT.md",
                        "mime_type": "text/markdown",
                        "size_bytes": 4096,
                        "is_active": True,
                    }],
                },
            }],
            "unmapped_hit_count": 1,
        }
        encoded = json.dumps(result.structured_content)
        for private_name in (
            "provider_locator",
            "external_id",
            "asset_id",
            "blob_id",
            "source_id",
            "embedding",
            "provider_score",
            "metadata",
            "raw",
        ):
            assert private_name not in encoded

    asyncio.run(exercise())
    assert retrieval_service.call == ("seaside", "immich", 4)


def test_retrieval_tool_reports_unavailable_configuration() -> None:
    server = create_server(QueryService(RecordingRepository()))

    async def exercise() -> None:
        async with Client(server) as client:
            result = await client.call_tool(
                "pdi_retrieve_resources",
                {"query": "photo", "provider": "immich"},
            )
        assert result.structured_content["error"]["code"] == (
            "provider_capability_unavailable"
        )

    asyncio.run(exercise())


def test_unsupported_retrieval_provider_is_rejected_by_mcp_schema() -> None:
    query_repository = RecordingRepository()

    class RetrievalServiceMustNotRun:
        def retrieve_resources(self, **kwargs):
            raise AssertionError("MCP schema should reject the provider")

    server = create_server(
        QueryService(query_repository),
        retrieval_service=RetrievalServiceMustNotRun(),
    )

    async def exercise() -> None:
        async with Client(server) as client:
            result = await client.call_tool(
                "pdi_retrieve_resources",
                {"query": "photo", "provider": "nextcloud"},
            )

        assert result.is_error is True
        assert result.structured_content is None

    asyncio.run(exercise())


def test_rich_retrieval_tool_has_tagged_input_and_bounded_payload() -> None:
    query_repository = RecordingRepository()

    class RecordingRichRetrievalService:
        def __init__(self) -> None:
            self.call = None

        def retrieve_resources(self, *, primary, filters, limit):
            self.call = (primary, filters, limit)
            return RichRetrievalResult(
                hits=(RichRetrievalHit(
                    resource=query_repository.summary,
                    source_rank=4,
                    matched_predicates=(
                        "media.ocr_text",
                        "media.captured_at",
                    ),
                    captured_at=datetime(2025, 1, 2, tzinfo=UTC),
                ),),
                stages=(
                    RetrievalStage(
                        "observation_text_primary",
                        0,
                        1,
                    ),
                    RetrievalStage("captured_at_filter", 1, 1),
                    RetrievalStage("final_limit", 1, 1),
                ),
                unmapped_hit_count=0,
            )

    rich_service = RecordingRichRetrievalService()
    server = create_server(
        QueryService(query_repository),
        rich_retrieval_service=rich_service,
    )

    async def exercise() -> None:
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            rich_tool = next(
                tool
                for tool in tools
                if tool.name == "pdi_rich_retrieve_resources"
            )
            result = await client.call_tool(
                "pdi_rich_retrieve_resources",
                {
                    "primary": {
                        "kind": "observation_text",
                        "query": "Cambridge",
                        "predicate": "media.ocr_text",
                    },
                    "filters": {
                        "captured_from": "2025-01-01T08:00:00+08:00",
                        "required_predicates": ["media.ocr_text"],
                    },
                    "limit": 20,
                },
            )

        assert len(tools) == 7
        primary_schema = rich_tool.input_schema["properties"]["primary"]
        assert primary_schema["discriminator"]["propertyName"] == "kind"
        assert len(primary_schema["oneOf"]) == 2
        assert result.structured_content == {
            "ok": True,
            "hits": [{
                "resource": {
                    "resource_ref": query_repository.resource_ref,
                    "resource_type": "file",
                    "display_name": "CURRENT_CONTEXT.md",
                    "pdi_first_observed_at": (
                        "2026-07-31T12:00:00+00:00"
                    ),
                    "sources": [{
                        "provider": "immich",
                        "location": "/library/CURRENT_CONTEXT.md",
                        "name": "CURRENT_CONTEXT.md",
                        "mime_type": "text/markdown",
                        "size_bytes": 4096,
                        "is_active": True,
                    }],
                },
                "source_rank": 4,
                "matched_predicates": [
                    "media.ocr_text",
                    "media.captured_at",
                ],
                "captured_at": "2025-01-02T00:00:00+00:00",
            }],
            "stages": [
                {
                    "stage": "observation_text_primary",
                    "input_count": 0,
                    "output_count": 1,
                },
                {
                    "stage": "captured_at_filter",
                    "input_count": 1,
                    "output_count": 1,
                },
                {
                    "stage": "final_limit",
                    "input_count": 1,
                    "output_count": 1,
                },
            ],
            "unmapped_hit_count": 0,
        }
        encoded = json.dumps(result.structured_content)
        assert len(encoded.encode()) < 10_000
        for private_name in (
            "provider_locator",
            "external_id",
            "asset_id",
            "blob_id",
            "source_id",
            "metadata",
            "raw",
        ):
            assert private_name not in encoded
        assert "Cambridge" not in encoded
        assert "observation body" not in encoded

    asyncio.run(exercise())
    assert rich_service.call is not None
    primary, filters, limit = rich_service.call
    assert primary.kind == "observation_text"
    assert primary.predicate == "media.ocr_text"
    assert filters.captured_from == datetime(2025, 1, 1, tzinfo=UTC)
    assert filters.required_predicates == ("media.ocr_text",)
    assert limit == 20


def test_rich_retrieval_mixed_primary_is_rejected_by_mcp_schema() -> None:
    server = create_server(QueryService(RecordingRepository()))

    async def exercise() -> None:
        async with Client(server) as client:
            result = await client.call_tool(
                "pdi_rich_retrieve_resources",
                {
                    "primary": {
                        "kind": "provider_semantic",
                        "query": "car",
                        "provider": "immich",
                        "predicate": "media.ocr_text",
                    }
                },
            )
        assert result.is_error is True
        assert result.structured_content is None

    asyncio.run(exercise())


def test_rich_retrieval_max_twenty_payload_stays_bounded() -> None:
    repository = RecordingRepository()
    result = RichRetrievalResult(
        hits=tuple(
            RichRetrievalHit(
                resource=repository.summary,
                source_rank=rank,
                matched_predicates=("media.ocr_text",),
            )
            for rank in range(1, 21)
        ),
        stages=(
            RetrievalStage("observation_text_primary", 0, 50),
            RetrievalStage("final_limit", 50, 20),
        ),
        unmapped_hit_count=0,
    )

    encoded = json.dumps(serialize_rich_retrieval_result(result))

    assert len(encoded.encode()) < 30_000
    assert "OCR body" not in encoded
    assert "document excerpt body" not in encoded
