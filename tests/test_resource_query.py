from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from pdi.query import (
    ContentSummary,
    InvalidQueryError,
    InvalidResourceRefError,
    QueryService,
    RecentResourcesQuery,
    ResourceDetail,
    ResourceNotFoundError,
    ResourceSearchQuery,
    ResourceSourceSummary,
    ResourceSummary,
    format_resource_ref,
    parse_resource_ref,
)


class StubResourceRepository:
    def __init__(
        self,
        summary: ResourceSummary,
        detail: ResourceDetail,
    ) -> None:
        self.summary = summary
        self.detail = detail
        self.recent_queries: list[RecentResourcesQuery] = []
        self.search_queries: list[ResourceSearchQuery] = []
        self.detail_ids: list[str] = []

    def list_recent_resources(
        self,
        query: RecentResourcesQuery,
    ) -> tuple[ResourceSummary, ...]:
        self.recent_queries.append(query)
        return (self.summary,)

    def search_resources(
        self,
        query: ResourceSearchQuery,
    ) -> tuple[ResourceSummary, ...]:
        self.search_queries.append(query)
        return (self.summary,)

    def get_resource_detail(
        self,
        asset_id: str,
    ) -> ResourceDetail | None:
        self.detail_ids.append(asset_id)
        expected_id = parse_resource_ref(self.detail.resource_ref)
        return self.detail if asset_id == expected_id else None


def _resource_models() -> tuple[ResourceSummary, ResourceDetail]:
    observed_at = datetime(2026, 7, 31, 12, tzinfo=UTC)
    active_source = ResourceSourceSummary(
        provider="immich",
        location="/photos/one.jpg",
        name="one.jpg",
        mime_type="image/jpeg",
        size_bytes=1024,
        is_active=True,
    )
    inactive_source = ResourceSourceSummary(
        provider="nextcloud",
        location="/archive/one.jpg",
        name="one.jpg",
        mime_type="image/jpeg",
        size_bytes=2048,
        is_active=False,
    )
    resource_ref = format_resource_ref(uuid4())
    summary = ResourceSummary(
        resource_ref=resource_ref,
        resource_type="file",
        display_name="one.jpg",
        pdi_first_observed_at=observed_at,
        sources=(active_source,),
    )
    detail = ResourceDetail(
        resource_ref=resource_ref,
        resource_type="file",
        display_name="one.jpg",
        pdi_first_observed_at=observed_at,
        sources=(active_source, inactive_source),
        content_variants=(
            ContentSummary("image/jpeg", 1024, "sha256-a"),
            ContentSummary("image/jpeg", 2048, "sha256-b"),
        ),
    )
    return summary, detail


def test_resource_ref_round_trip() -> None:
    asset_id = uuid4()
    resource_ref = format_resource_ref(asset_id)

    assert resource_ref == f"pdi:resource:{asset_id}"
    assert parse_resource_ref(resource_ref) == str(asset_id)


@pytest.mark.parametrize(
    "resource_ref",
    [
        "asset:resource:00000000-0000-0000-0000-000000000000",
        "pdi:resource:not-a-uuid",
        "pdi:resource:00000000000000000000000000000000",
    ],
)
def test_resource_ref_rejects_invalid_values(resource_ref: str) -> None:
    with pytest.raises(InvalidResourceRefError):
        parse_resource_ref(resource_ref)


def test_resource_dtos_are_immutable_and_support_projection_edges() -> None:
    summary, detail = _resource_models()
    zero_source_summary = ResourceSummary(
        resource_ref=format_resource_ref(uuid4()),
        resource_type="file",
        display_name="detached.txt",
        pdi_first_observed_at=summary.pdi_first_observed_at,
        sources=[],
    )

    with pytest.raises(FrozenInstanceError):
        summary.display_name = "changed"

    assert zero_source_summary.sources == ()
    assert len(detail.sources) == 2
    assert detail.sources[1].is_active is False
    assert len(detail.content_variants) == 2
    assert detail.content_variants[0].checksum == "sha256-a"
    assert detail.content_variants[1].checksum == "sha256-b"
    assert [field.name for field in fields(ContentSummary)] == [
        "mime_type",
        "size_bytes",
        "checksum",
    ]

    public_fields = {
        field.name
        for model in (
            ResourceSourceSummary,
            ResourceSummary,
            ContentSummary,
            ResourceDetail,
        )
        for field in fields(model)
    }
    assert "asset_id" not in public_fields
    assert "blob_id" not in public_fields
    assert "source_id" not in public_fields
    assert "external_id" not in public_fields


def test_query_service_builds_validated_queries() -> None:
    summary, detail = _resource_models()
    repository = StubResourceRepository(summary, detail)
    now = datetime(2026, 7, 31, 12, tzinfo=UTC)
    service = QueryService(repository, clock=lambda: now)

    assert service.list_recent_resources(
        days=7,
        provider="immich",
        resource_type="file",
        mime_type="image/jpeg",
        path_prefix="/photos",
        limit=20,
    ) == (summary,)
    assert repository.recent_queries == [
        RecentResourcesQuery(
            created_since=now - timedelta(days=7),
            provider="immich",
            resource_type="file",
            mime_type="image/jpeg",
            path_prefix="/photos",
            limit=20,
        )
    ]

    assert service.search_resources(
        query=" one ",
        provider="immich",
        limit=10,
    ) == (summary,)
    assert repository.search_queries[0].query == "one"
    assert service.get_resource(detail.resource_ref) is detail
    assert repository.detail_ids == [
        parse_resource_ref(detail.resource_ref)
    ]


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [
        ("recent", {"days": 0}),
        ("recent", {"days": True}),
        ("recent", {"days": 1_000_000_000}),
        ("recent", {"limit": 0}),
        ("recent", {"limit": 101}),
        ("recent", {"provider": ""}),
        ("recent", {"resource_type": "photo"}),
        ("search", {"query": ""}),
        ("search", {"query": "photo", "limit": 101}),
    ],
)
def test_query_service_rejects_invalid_arguments(
    method: str,
    kwargs: dict,
) -> None:
    summary, detail = _resource_models()
    service = QueryService(StubResourceRepository(summary, detail))

    with pytest.raises(InvalidQueryError):
        if method == "recent":
            service.list_recent_resources(**kwargs)
        else:
            service.search_resources(**kwargs)


def test_valid_missing_resource_is_distinct_from_invalid_ref() -> None:
    summary, detail = _resource_models()
    service = QueryService(StubResourceRepository(summary, detail))
    missing_ref = format_resource_ref(uuid4())

    with pytest.raises(ResourceNotFoundError):
        service.get_resource(missing_ref)

    with pytest.raises(InvalidResourceRefError):
        service.get_resource("pdi:resource:invalid")

    assert UUID(parse_resource_ref(missing_ref))
