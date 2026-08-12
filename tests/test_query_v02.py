from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from pdi.query import (
    InvalidQueryError,
    QueryService,
    ResourceAggregationQuery,
    ResourceAggregationResult,
    ResourceFilters,
    ResourceGroupBy,
    ResourceListPageQuery,
    ResourceSearchPageQuery,
    ResourceSourceSummary,
    ResourceSummary,
    format_resource_ref,
)
from pdi.query.cursor import encode_cursor


def _summary(
    *,
    title: str,
    observed_at: datetime,
) -> ResourceSummary:
    return ResourceSummary(
        resource_ref=format_resource_ref(uuid4()),
        resource_type="file",
        display_name=title,
        pdi_first_observed_at=observed_at,
        sources=(
            ResourceSourceSummary(
                provider="immich",
                location=f"/photos/{title}",
                name=title,
                mime_type="image/jpeg",
                size_bytes=1,
                is_active=True,
            ),
        ),
    )


class RecordingRepository:
    def __init__(self, now: datetime) -> None:
        self.list_batches: list[tuple[ResourceSummary, ...]] = []
        self.search_batches: list[tuple[ResourceSummary, ...]] = []
        self.list_queries: list[ResourceListPageQuery] = []
        self.search_queries: list[ResourceSearchPageQuery] = []
        self.aggregation_queries: list[ResourceAggregationQuery] = []
        self.default_summary = _summary(
            title="one.jpg",
            observed_at=now - timedelta(days=1),
        )

    def list_resource_page(
        self,
        query: ResourceListPageQuery,
    ) -> tuple[ResourceSummary, ...]:
        self.list_queries.append(query)
        if self.list_batches:
            return self.list_batches.pop(0)
        return (self.default_summary,)

    def search_resource_page(
        self,
        query: ResourceSearchPageQuery,
    ) -> tuple[ResourceSummary, ...]:
        self.search_queries.append(query)
        if self.search_batches:
            return self.search_batches.pop(0)
        return (self.default_summary,)

    def aggregate_resources(
        self,
        query: ResourceAggregationQuery,
    ) -> ResourceAggregationResult:
        self.aggregation_queries.append(query)
        return ResourceAggregationResult(
            time_basis="pdi_first_observed_at",
            time_range=query.time_range,
            applied_filters=query.filters,
            group_by=query.group_by,
            total_count=0,
            buckets=(),
            buckets_truncated=False,
        )


def test_aggregation_normalizes_time_and_builds_typed_query() -> None:
    now = datetime(2026, 8, 12, 12, tzinfo=UTC)
    repository = RecordingRepository(now)
    service = QueryService(repository, clock=lambda: now)
    observed_from = datetime(
        2026,
        8,
        11,
        8,
        tzinfo=timezone(timedelta(hours=8)),
    )

    result = service.aggregate_resources(
        group_by="provider",
        observed_from=observed_from,
        provider="immich",
        mime_category="IMAGE",
    )

    query = repository.aggregation_queries[0]
    assert query.group_by is ResourceGroupBy.PROVIDER
    assert query.time_range.observed_from == datetime(
        2026,
        8,
        11,
        tzinfo=UTC,
    )
    assert query.time_range.observed_to is None
    assert query.filters == ResourceFilters(
        provider="immich",
        resource_type=None,
        mime_type=None,
        mime_category="image",
        path_prefix=None,
    )
    assert result.total_count == 0
    with pytest.raises(FrozenInstanceError):
        result.total_count = 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"observed_from": datetime(2026, 8, 1)},
        {
            "observed_from": datetime(2026, 8, 2, tzinfo=UTC),
            "observed_to": datetime(2026, 8, 2, tzinfo=UTC),
        },
        {
            "observed_from": datetime(2026, 8, 3, tzinfo=UTC),
            "observed_to": datetime(2026, 8, 2, tzinfo=UTC),
        },
        {"mime_type": "image/jpeg", "mime_category": "image"},
        {"mime_category": "image/jpeg"},
        {"group_by": "arbitrary"},
    ],
)
def test_aggregation_rejects_invalid_arguments(kwargs: dict) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    service = QueryService(RecordingRepository(now), clock=lambda: now)

    with pytest.raises(InvalidQueryError):
        service.aggregate_resources(**kwargs)


def test_day_aggregation_requires_bounded_366_day_range() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    service = QueryService(RecordingRepository(now), clock=lambda: now)

    with pytest.raises(InvalidQueryError):
        service.aggregate_resources(group_by="day")
    with pytest.raises(InvalidQueryError):
        service.aggregate_resources(
            group_by="day",
            observed_from=now - timedelta(days=367),
            observed_to=now,
        )

    service.aggregate_resources(
        group_by="day",
        observed_from=now - timedelta(days=366),
        observed_to=now,
    )


def test_recent_cursor_round_trip_keeps_snapshot_and_allows_limit_change() -> None:
    now = datetime(2026, 8, 12, 12, tzinfo=UTC)
    repository = RecordingRepository(now)
    first = _summary(
        title="first.jpg",
        observed_at=now - timedelta(hours=1),
    )
    lookahead = _summary(
        title="second.jpg",
        observed_at=now - timedelta(hours=2),
    )
    repository.list_batches = [(first, lookahead), (lookahead,)]
    service = QueryService(repository, clock=lambda: now)

    first_page = service.list_resource_page(days=7, limit=1)
    assert first_page.resources == (first,)
    assert first_page.next_cursor is not None
    second_page = service.list_resource_page(
        days=7,
        limit=2,
        cursor=first_page.next_cursor,
    )

    first_query, second_query = repository.list_queries
    assert first_query.limit == 2
    assert second_query.limit == 3
    assert first_query.snapshot_to == now
    assert second_query.snapshot_to == now
    assert second_query.after_observed_at == first.pdi_first_observed_at
    assert second_page.resources == (lookahead,)
    assert second_page.next_cursor is None


def test_search_cursor_round_trip_and_query_binding() -> None:
    now = datetime(2026, 8, 12, 12, tzinfo=UTC)
    repository = RecordingRepository(now)
    first = _summary(title="A", observed_at=now - timedelta(hours=1))
    second = _summary(title="B", observed_at=now - timedelta(hours=2))
    repository.search_batches = [(first, second), (second,)]
    service = QueryService(repository, clock=lambda: now)

    first_page = service.search_resource_page(query="photo", limit=1)
    assert first_page.next_cursor is not None
    service.search_resource_page(
        query="photo",
        limit=1,
        cursor=first_page.next_cursor,
    )
    assert repository.search_queries[1].after_title == "A"

    with pytest.raises(InvalidQueryError):
        service.search_resource_page(
            query="different",
            cursor=first_page.next_cursor,
        )


def test_cursor_rejects_malformed_tampered_wrong_and_mismatched_values() -> None:
    now = datetime(2026, 8, 12, 12, tzinfo=UTC)
    repository = RecordingRepository(now)
    first = _summary(title="A", observed_at=now - timedelta(hours=1))
    second = _summary(title="B", observed_at=now - timedelta(hours=2))
    repository.list_batches = [(first, second)]
    service = QueryService(repository, clock=lambda: now)
    cursor = service.list_resource_page(limit=1).next_cursor
    assert cursor is not None

    invalid_values = [
        "not-base64!",
        cursor + "=",
        cursor[:-1] + ("A" if cursor[-1] != "A" else "B"),
        "a" * 4097,
    ]
    for invalid_cursor in invalid_values:
        with pytest.raises(InvalidQueryError):
            service.list_resource_page(cursor=invalid_cursor)

    wrong_version = encode_cursor(
        {
            "version": 999,
            "operation": "recent",
            "fingerprint": "unused",
        }
    )
    with pytest.raises(InvalidQueryError):
        service.list_resource_page(cursor=wrong_version)

    with pytest.raises(InvalidQueryError):
        service.search_resource_page(query="A", cursor=cursor)
    with pytest.raises(InvalidQueryError):
        service.list_resource_page(provider="nextcloud", cursor=cursor)


def test_page_rejects_days_range_conflict_and_invalid_limit() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    service = QueryService(RecordingRepository(now), clock=lambda: now)

    with pytest.raises(InvalidQueryError):
        service.list_resource_page(
            days=7,
            observed_from=now - timedelta(days=1),
        )
    for invalid_limit in (0, 101, True):
        with pytest.raises(InvalidQueryError):
            service.list_resource_page(limit=invalid_limit)
