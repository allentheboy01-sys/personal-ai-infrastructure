import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid5

import pytest

from pdi.query import ResourcePage, ResourceSourceSummary, ResourceSummary
from pdi.resource_query import (
    InvalidResourceQueryContinuationError,
    InvalidResourceQueryFiltersError,
    InvalidResourceQuerySortError,
    MetadataTextPrimary,
    ObservationTextPrimary,
    PathTreePrimary,
    PersonLabelPrimary,
    ProviderSemanticPrimary,
    RecentPrimary,
    ResourceQueryFilters,
    ResourceQueryProjectionError,
    ResourceQueryService,
    ResourceQuerySort,
    serialize_resource_query_result,
    serialized_result_bytes,
)
from pdi.retrieval import ProviderCapabilityUnavailableError
from pdi.rich_retrieval import (
    RichFilterSignals,
    RichRetrievalHit,
    RichRetrievalResult,
    RetrievalStage,
)


NOW = datetime(2026, 8, 1, tzinfo=UTC)
NAMESPACE = UUID("c20fd0d2-d59a-4fd7-a3c7-d0c883453d91")


def _resource(
    title: str,
    *,
    path: str | None = None,
    provider: str = "nextcloud",
    mime_type: str = "text/markdown",
    observed_at: datetime = NOW - timedelta(days=1),
) -> ResourceSummary:
    return ResourceSummary(
        resource_ref=f"pdi:resource:{uuid5(NAMESPACE, title + (path or ''))}",
        resource_type="file",
        display_name=title,
        pdi_first_observed_at=observed_at,
        sources=(ResourceSourceSummary(
            provider=provider,
            location=path,
            name=title,
            mime_type=mime_type,
            size_bytes=128,
            is_active=True,
        ),),
    )


class FakeQueryService:
    def __init__(
        self,
        *,
        search: tuple[ResourceSummary, ...] = (),
        listed: tuple[ResourceSummary, ...] = (),
    ) -> None:
        self.search = search
        self.listed = listed
        self.search_calls: list[dict[str, object]] = []
        self.list_calls: list[dict[str, object]] = []

    @staticmethod
    def _page(resources, *, limit, cursor):
        offset = 0 if cursor is None else int(cursor.removeprefix("offset:"))
        page = resources[offset:offset + limit]
        next_offset = offset + len(page)
        return ResourcePage(
            resources=tuple(page),
            next_cursor=(
                f"offset:{next_offset}"
                if next_offset < len(resources)
                else None
            ),
        )

    def search_resource_page(self, **kwargs):
        self.search_calls.append(kwargs)
        return self._page(
            self.search,
            limit=kwargs["limit"],
            cursor=kwargs["cursor"],
        )

    def list_resource_page(self, **kwargs):
        self.list_calls.append(kwargs)
        return self._page(
            self.listed,
            limit=kwargs["limit"],
            cursor=kwargs["cursor"],
        )


class BenchmarkQueryService(FakeQueryService):
    """Exercise fixture routing before returning repository-like pages."""

    def search_resource_page(self, **kwargs):
        self.search_calls.append(kwargs)
        needle = kwargs["query"].casefold()
        observed_from = kwargs["observed_from"]
        observed_to = kwargs["observed_to"]
        matches = tuple(
            resource
            for resource in self.search
            if needle in resource.display_name.casefold()
            and (
                observed_from is None
                or resource.pdi_first_observed_at >= observed_from
            )
            and (
                observed_to is None
                or resource.pdi_first_observed_at < observed_to
            )
        )
        return self._page(
            matches,
            limit=kwargs["limit"],
            cursor=kwargs["cursor"],
        )


class FakeRichService:
    def __init__(
        self,
        resources: tuple[ResourceSummary, ...] = (),
        *,
        signals: dict[str, RichFilterSignals] | None = None,
    ) -> None:
        self.resources = resources
        self.signals = signals or {}
        self.select_calls: list[dict[str, object]] = []
        self.signal_calls: list[dict[str, object]] = []

    def select_resources(self, **kwargs):
        self.select_calls.append(kwargs)
        limit = kwargs["candidate_limit"]
        hits = tuple(
            RichRetrievalHit(
                resource=resource,
                source_rank=index,
                matched_predicates=(),
            )
            for index, resource in enumerate(
                self.resources[:limit],
                start=1,
            )
        )
        return RichRetrievalResult(
            hits=hits,
            stages=(RetrievalStage(
                "primary",
                0,
                len(hits),
            ), RetrievalStage("final_limit", len(hits), len(hits))),
            unmapped_hit_count=0,
        )

    def load_filter_signals(self, **kwargs):
        self.signal_calls.append(kwargs)
        return {
            ref: self.signals[ref]
            for ref in kwargs["resource_refs"]
        }


def _signal(
    resource: ResourceSummary,
    *,
    captured_at=None,
    modified_at=None,
    predicates=frozenset(),
):
    return RichFilterSignals(
        resource_ref=resource.resource_ref,
        source_metadata_match=True,
        captured_at=captured_at,
        file_modified_at=modified_at,
        current_predicates=frozenset(predicates),
    )


def test_benchmark_a_metadata_routing_relevance_and_compact_bounds() -> None:
    fixture = json.loads(
        Path("tests/fixtures/resource_query_benchmark_a.json").read_text()
    )
    matching = tuple(
        _resource(
            title,
            path=f"/documents/modeling/{title}",
            observed_at=NOW - timedelta(days=index),
        )
        for index, title in enumerate(fixture["matching_titles"], start=1)
    )
    distractors = tuple(
        _resource(
            title,
            path=f"/documents/other/{title}",
            observed_at=NOW - timedelta(days=index),
        )
        for index, title in enumerate(
            fixture["distractor_titles"],
            start=1,
        )
    )
    outside_time = tuple(
        _resource(
            title,
            path=f"/documents/archive/{title}",
            observed_at=NOW - timedelta(days=45 + index),
        )
        for index, title in enumerate(
            fixture["outside_time_titles"],
            start=1,
        )
    )
    corpus = matching + distractors + outside_time
    expected = fixture["expected"]
    assert len(corpus) == expected["candidate_count"]
    query = BenchmarkQueryService(search=tuple(reversed(corpus)))
    rich = FakeRichService()
    result = ResourceQueryService(
        query,
        rich,
        clock=lambda: NOW,
    ).query_resources(
        primary=MetadataTextPrimary(
            "metadata_text",
            fixture["query"],
        ),
        filters=ResourceQueryFilters(
            observed_from=datetime.fromisoformat(fixture["observed_from"]),
            observed_to=datetime.fromisoformat(fixture["observed_to"]),
            mime_category="text",
        ),
    )

    assert result.selection_status == "complete"
    assert result.scanned_count == expected["scanned_count"]
    assert len(result.resources) == expected["returned_count"]
    assert result.resources[0].match_basis == "title_exact"
    assert result.continuation is None
    assert len(rich.select_calls) == expected[
        "provider_semantic_call_count"
    ]
    assert serialized_result_bytes(result) == expected[
        "serialized_bytes"
    ]
    assert serialized_result_bytes(result) <= 8192
    assert len(query.search_calls) == expected["application_call_count"]
    assert int(result.continuation is not None) == expected[
        "agent_pagination_required"
    ]


def test_provider_semantic_is_explicit_once_and_never_falls_back() -> None:
    photo = _resource(
        "summit.jpg",
        path="/photos/summit.jpg",
        provider="immich",
        mime_type="image/jpeg",
    )
    rich = FakeRichService((photo,))
    query = FakeQueryService()
    service = ResourceQueryService(query, rich, clock=lambda: NOW)

    result = service.query_resources(
        primary=ProviderSemanticPrimary(
            "provider_semantic",
            "conference summit",
            "immich",
        ),
    )

    assert [item.resource_ref for item in result.resources] == [
        photo.resource_ref
    ]
    assert len(rich.select_calls) == 1
    assert query.search_calls == query.list_calls == []

    with pytest.raises(ProviderCapabilityUnavailableError):
        service.query_resources(
            primary=ProviderSemanticPrimary(
                "provider_semantic",
                "conference summit",
                "nextcloud",
            ),
        )
    with pytest.raises(InvalidResourceQueryFiltersError):
        service.query_resources(
            primary=ProviderSemanticPrimary(
                "provider_semantic",
                "conference summit",
                "immich",
            ),
            filters=ResourceQueryFilters(provider="nextcloud"),
        )
    with pytest.raises(InvalidResourceQuerySortError):
        service.query_resources(
            primary=ProviderSemanticPrimary(
                "provider_semantic",
                "conference summit",
                "immich",
            ),
            sort=ResourceQuerySort("captured_at", "desc"),
        )


def test_rich_primary_is_capped_by_the_public_snapshot() -> None:
    visible = _resource("visible.jpg", observed_at=NOW - timedelta(seconds=1))
    future = _resource("future.jpg", observed_at=NOW + timedelta(seconds=1))
    result = ResourceQueryService(
        FakeQueryService(),
        FakeRichService((future, visible)),
        clock=lambda: NOW,
    ).query_resources(
        primary=ProviderSemanticPrimary(
            "provider_semantic",
            "summit",
            "immich",
        ),
    )

    assert [item.resource_ref for item in result.resources] == [
        visible.resource_ref
    ]


@pytest.mark.parametrize(
    ("primary", "expected_kind"),
    [
        (
            ObservationTextPrimary(
                "observation_text",
                "equation",
                "document.text_excerpt",
            ),
            "observation_text",
        ),
        (PersonLabelPrimary("person_label", "Alice", "immich"), "person_label"),
    ],
)
def test_observation_and_exact_person_primaries_preserve_one_strategy(
    primary,
    expected_kind,
) -> None:
    resource = _resource("one.md", path="/docs/one.md")
    rich = FakeRichService((resource,))
    service = ResourceQueryService(FakeQueryService(), rich, clock=lambda: NOW)

    result = service.query_resources(primary=primary)

    assert result.query_kind == expected_kind
    assert len(rich.select_calls) == 1
    selected_primary = rich.select_calls[0]["primary"]
    assert selected_primary.kind == expected_kind
    if expected_kind == "person_label":
        assert selected_primary.label == "Alice"


def test_path_tree_returns_normalized_paths_and_distinguishes_duplicates() -> None:
    first = _resource("index.md", path="/projects/a/index.md")
    second = _resource("index.md", path="/projects/b/index.md")
    query = FakeQueryService(listed=(second, first))
    result = ResourceQueryService(
        query,
        FakeRichService(),
        clock=lambda: NOW,
    ).query_resources(
        primary=PathTreePrimary("path_tree", "/projects"),
    )

    assert [item.relative_path for item in result.resources] == [
        "projects/a/index.md",
        "projects/b/index.md",
    ]
    assert len({item.resource_ref for item in result.resources}) == 2
    assert query.list_calls[0]["path_prefix"] == "/projects"

    with pytest.raises(InvalidResourceQueryFiltersError):
        ResourceQueryService(query, FakeRichService()).query_resources(
            primary=PathTreePrimary("path_tree", "/projects"),
            filters=ResourceQueryFilters(path_prefix="/other"),
        )


def test_metadata_path_match_exposes_only_safe_relative_path() -> None:
    path_match = _resource(
        "notes.md",
        path="/documents/mathematical-modeling/notes.md",
    )
    unsafe = _resource(
        "other.md",
        path="https://cloud.example/secret/mathematical-modeling/other.md",
    )
    service = ResourceQueryService(
        FakeQueryService(search=(path_match, unsafe)),
        FakeRichService(),
        clock=lambda: NOW,
    )

    with pytest.raises(ResourceQueryProjectionError):
        service.query_resources(
            primary=MetadataTextPrimary(
                "metadata_text",
                "mathematical-modeling",
            ),
        )

    result = ResourceQueryService(
        FakeQueryService(search=(path_match,)),
        FakeRichService(),
        clock=lambda: NOW,
    ).query_resources(
        primary=MetadataTextPrimary(
            "metadata_text",
            "mathematical-modeling",
        ),
    )
    assert result.resources[0].match_basis == "path_substring"
    assert result.resources[0].relative_path == (
        "documents/mathematical-modeling/notes.md"
    )


def test_metadata_path_sort_uses_safe_path_even_when_title_matches() -> None:
    second = _resource("math.md", path="/documents/z/math.md")
    first = _resource("math.md", path="/documents/a/math.md")
    result = ResourceQueryService(
        FakeQueryService(search=(second, first)),
        FakeRichService(),
        clock=lambda: NOW,
    ).query_resources(
        primary=MetadataTextPrimary("metadata_text", "math.md"),
        sort=ResourceQuerySort("path", "asc"),
    )

    assert [item.relative_path for item in result.resources] == [
        "documents/a/math.md",
        "documents/z/math.md",
    ]


def test_time_sort_uses_exact_signal_and_never_substitutes() -> None:
    captured = _resource("captured.jpg", path="/photos/captured.jpg")
    missing = _resource(
        "missing.jpg",
        path="/photos/missing.jpg",
        observed_at=NOW,
    )
    signals = {
        captured.resource_ref: _signal(
            captured,
            captured_at=NOW - timedelta(days=10),
            predicates={"media.captured_at"},
        ),
        missing.resource_ref: _signal(missing),
    }
    result = ResourceQueryService(
        FakeQueryService(listed=(missing, captured)),
        FakeRichService(signals=signals),
        clock=lambda: NOW,
    ).query_resources(
        primary=RecentPrimary("recent"),
        sort=ResourceQuerySort("captured_at", "desc"),
    )

    assert [item.resource_ref for item in result.resources] == [
        captured.resource_ref
    ]
    assert result.resources[0].time_basis == "media.captured_at"
    assert result.resources[0].relevant_time == NOW - timedelta(days=10)


def test_file_modified_sort_uses_only_file_modified_signal() -> None:
    modified = _resource("modified.md", path="/docs/modified.md")
    captured_only = _resource("captured.md", path="/docs/captured.md")
    signals = {
        modified.resource_ref: _signal(
            modified,
            modified_at=NOW - timedelta(hours=2),
            predicates={"file.modified_at"},
        ),
        captured_only.resource_ref: _signal(
            captured_only,
            captured_at=NOW - timedelta(hours=1),
            predicates={"media.captured_at"},
        ),
    }
    result = ResourceQueryService(
        FakeQueryService(listed=(captured_only, modified)),
        FakeRichService(signals=signals),
        clock=lambda: NOW,
    ).query_resources(
        primary=RecentPrimary("recent"),
        sort=ResourceQuerySort("file_modified_at", "desc"),
    )

    assert [item.resource_ref for item in result.resources] == [
        modified.resource_ref
    ]
    assert result.resources[0].time_basis == "file.modified_at"
    assert result.resources[0].relevant_time == NOW - timedelta(hours=2)


def test_top_n_has_no_continuation_but_explicit_traversal_does() -> None:
    resources = tuple(
        _resource(f"file-{index}.md", path=f"/tree/file-{index:02}.md")
        for index in range(20)
    )
    service = ResourceQueryService(
        FakeQueryService(listed=resources),
        FakeRichService(),
        clock=lambda: NOW,
    )
    ordinary = service.query_resources(
        primary=PathTreePrimary("path_tree", "/tree"),
        limit=10,
    )
    first = service.query_resources(
        primary=PathTreePrimary("path_tree", "/tree"),
        limit=10,
        continuable=True,
    )
    second = service.query_resources(
        primary=PathTreePrimary("path_tree", "/tree"),
        limit=10,
        continuable=True,
        continuation=first.continuation,
    )

    assert ordinary.continuation is None
    assert first.continuation is not None
    assert second.continuation is None
    assert {item.resource_ref for item in first.resources}.isdisjoint(
        {item.resource_ref for item in second.resources}
    )

    with pytest.raises(InvalidResourceQueryContinuationError):
        service.query_resources(
            primary=PathTreePrimary("path_tree", "/different"),
            continuable=True,
            continuation=first.continuation,
        )


def test_internal_pages_share_snapshot_and_scan_limit_is_partial() -> None:
    resources = tuple(
        _resource(f"math-{index}.md", path=f"/docs/math-{index}.md")
        for index in range(105)
    )
    query = FakeQueryService(search=resources)
    result = ResourceQueryService(
        query,
        FakeRichService(),
        clock=lambda: NOW,
    ).query_resources(
        primary=MetadataTextPrimary("metadata_text", "math"),
        scan_limit=100,
    )

    assert result.selection_status == "bounded_partial"
    assert result.bound_reason == "scan_limit"
    assert result.scanned_count == 100
    assert {call["observed_to"] for call in query.search_calls} == {NOW}


def test_timeout_is_sanitized_bounded_partial() -> None:
    resources = tuple(
        _resource(f"math-{index}.md", path=f"/docs/math-{index}.md")
        for index in range(101)
    )
    ticks = iter((0.0, 0.0, 31.0, 31.0))
    result = ResourceQueryService(
        FakeQueryService(search=resources),
        FakeRichService(),
        clock=lambda: NOW,
        monotonic_clock=lambda: next(ticks, 31.0),
    ).query_resources(
        primary=MetadataTextPrimary("metadata_text", "math"),
    )

    assert result.selection_status == "bounded_partial"
    assert result.bound_reason == "timeout"
    assert result.scanned_count <= 100


def test_serialized_cap_and_compact_projection_exclude_internal_data() -> None:
    long_segment = "x" * 980
    resources = tuple(
        _resource(
            f"file-{index}.md",
            path=f"/tree/{long_segment}-{index}/file.md",
        )
        for index in range(50)
    )
    result = ResourceQueryService(
        FakeQueryService(listed=resources),
        FakeRichService(),
        clock=lambda: NOW,
    ).query_resources(
        primary=PathTreePrimary("path_tree", "/tree"),
        limit=50,
        continuable=True,
    )
    payload = serialize_resource_query_result(result)
    encoded = json.dumps(payload, ensure_ascii=False)

    assert serialized_result_bytes(result) <= 64 * 1024
    assert result.selection_status == "bounded_partial"
    assert result.bound_reason == "serialized_byte_limit"
    for forbidden in (
        "observations",
        "provider_locator",
        "external_id",
        "metadata",
        "raw",
        "http://",
        "https://",
    ):
        assert forbidden not in encoded


@pytest.mark.parametrize("limit", [0, 51, True])
def test_result_limit_is_hard_bounded(limit) -> None:
    with pytest.raises(InvalidResourceQueryFiltersError):
        ResourceQueryService(
            FakeQueryService(),
            FakeRichService(),
        ).query_resources(
            primary=RecentPrimary("recent"),
            limit=limit,
        )


@pytest.mark.parametrize("scan_limit", [0, 2001, True])
def test_scan_limit_is_hard_bounded(scan_limit) -> None:
    with pytest.raises(InvalidResourceQueryFiltersError):
        ResourceQueryService(
            FakeQueryService(),
            FakeRichService(),
        ).query_resources(
            primary=RecentPrimary("recent"),
            scan_limit=scan_limit,
        )
