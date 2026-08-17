from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pdi.query import InvalidQueryError, ResourceSummary, format_resource_ref
from pdi.rich_retrieval import (
    MAX_PRIMARY_CANDIDATE_LIMIT,
    ObservationTextPrimary,
    PRIMARY_CANDIDATE_LIMIT,
    ProviderSemanticPrimary,
    RichCandidate,
    RichFilterSignals,
    RichFilters,
    RichRetrievalService,
)
from pdi.retrieval import (
    ResourceRetrievalHit,
    ResourceRetrievalResult,
)


NOW = datetime(2026, 8, 15, tzinfo=UTC)


def _summary(name: str, *, observed_at: datetime = NOW) -> ResourceSummary:
    return ResourceSummary(
        resource_ref=format_resource_ref(uuid4()),
        resource_type="file",
        display_name=name,
        pdi_first_observed_at=observed_at,
        sources=(),
    )


class StubRichRepository:
    def __init__(
        self,
        *,
        candidates: tuple[RichCandidate, ...] = (),
        signals: dict[str, RichFilterSignals] | None = None,
    ) -> None:
        self.candidates = candidates
        self.signals = signals or {}
        self.search_calls = []
        self.filter_calls = []

    def search_current_observation_text(self, *, primary, limit):
        self.search_calls.append((primary, limit))
        return self.candidates

    def load_rich_filter_signals(self, *, resource_refs, filters):
        self.filter_calls.append((resource_refs, filters))
        return self.signals


class StubRetrievalService:
    def __init__(self, result: ResourceRetrievalResult) -> None:
        self.result = result
        self.calls = []

    def retrieve_resources(self, *, query, provider, limit):
        self.calls.append((query, provider, limit))
        return self.result


def _provider_result(
    resources_and_ranks: tuple[tuple[ResourceSummary, int], ...],
    *,
    unmapped: int = 0,
) -> ResourceRetrievalResult:
    return ResourceRetrievalResult(
        hits=tuple(
            ResourceRetrievalHit(
                resource=resource,
                rank=rank,
                provider="immich",
                retrieval_kind="semantic",
            )
            for resource, rank in resources_and_ranks
        ),
        provider="immich",
        retrieval_kind="semantic",
        unmapped_hit_count=unmapped,
    )


def _signals(
    resource: ResourceSummary,
    *,
    source_match: bool = True,
    captured_at: datetime | None = None,
    file_modified_at: datetime | None = None,
    predicates: frozenset[str] = frozenset(),
) -> RichFilterSignals:
    return RichFilterSignals(
        resource_ref=resource.resource_ref,
        source_metadata_match=source_match,
        captured_at=captured_at,
        file_modified_at=file_modified_at,
        current_predicates=predicates,
    )


def test_primary_dtos_are_immutable_and_exactly_one_is_required() -> None:
    primary = ProviderSemanticPrimary(
        kind="provider_semantic",
        query="car",
        provider="immich",
    )
    with pytest.raises(FrozenInstanceError):
        primary.query = "beach"

    class MixedPrimary:
        query = "car"
        provider = "immich"
        predicate = "media.ocr_text"

    with pytest.raises(InvalidQueryError):
        RichRetrievalService(StubRichRepository()).retrieve_resources(
            primary=MixedPrimary(),
        )


@pytest.mark.parametrize(
    "primary",
    [
        ProviderSemanticPrimary("provider_semantic", "", "immich"),
    ],
)
def test_primary_validation(primary) -> None:
    with pytest.raises(InvalidQueryError):
        RichRetrievalService(StubRichRepository()).retrieve_resources(
            primary=primary,
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ProviderSemanticPrimary(
            "provider_semantic",
            "car",
            "nextcloud",
        ),
        lambda: ObservationTextPrimary(
            "observation_text",
            "text",
            "unknown.predicate",
        ),
    ],
)
def test_tagged_primary_dtos_reject_unsupported_variants(factory) -> None:
    with pytest.raises(ValidationError):
        factory()


@pytest.mark.parametrize("limit", [0, 21, True, 1.5])
def test_final_limit_is_bounded(limit) -> None:
    with pytest.raises(InvalidQueryError):
        RichRetrievalService(StubRichRepository()).retrieve_resources(
            primary=ObservationTextPrimary(
                "observation_text",
                "text",
                "media.ocr_text",
            ),
            limit=limit,
        )


def test_candidate_bound_rank_gaps_no_refill_and_unmapped_count() -> None:
    first = _summary("first.jpg")
    fourth = _summary("fourth.jpg")
    retrieval = StubRetrievalService(
        _provider_result(((first, 1), (fourth, 4)), unmapped=2)
    )
    repository = StubRichRepository(signals={
        first.resource_ref: _signals(first, source_match=True),
        fourth.resource_ref: _signals(fourth, source_match=False),
    })
    result = RichRetrievalService(
        repository,
        retrieval,
    ).retrieve_resources(
        primary=ProviderSemanticPrimary(
            "provider_semantic",
            "  car  ",
            "immich",
        ),
        filters=RichFilters(provider="immich"),
        limit=10,
    )

    assert PRIMARY_CANDIDATE_LIMIT == 50
    assert MAX_PRIMARY_CANDIDATE_LIMIT == 100
    assert retrieval.calls == [("car", "immich", 50)]
    assert [hit.source_rank for hit in result.hits] == [1]
    assert result.unmapped_hit_count == 2
    assert [(stage.stage, stage.input_count, stage.output_count) for stage in result.stages] == [
        ("provider_semantic_primary", 0, 2),
        ("source_metadata_filter", 2, 1),
        ("final_limit", 1, 1),
    ]


def test_captured_range_is_utc_from_inclusive_to_exclusive() -> None:
    at_from = _summary("from.jpg")
    before_to = _summary("before-to.jpg")
    at_to = _summary("to.jpg")
    missing = _summary(
        "missing.jpg",
        observed_at=NOW - timedelta(days=365),
    )
    candidates = tuple(
        RichCandidate(resource, index)
        for index, resource in enumerate(
            (at_from, before_to, at_to, missing),
            start=1,
        )
    )
    repository = StubRichRepository(
        candidates=candidates,
        signals={
            at_from.resource_ref: _signals(at_from, captured_at=NOW),
            before_to.resource_ref: _signals(
                before_to,
                captured_at=NOW + timedelta(hours=23),
            ),
            at_to.resource_ref: _signals(
                at_to,
                captured_at=NOW + timedelta(days=1),
            ),
            missing.resource_ref: _signals(missing, captured_at=None),
        },
    )
    result = RichRetrievalService(repository).retrieve_resources(
        primary=ObservationTextPrimary(
            "observation_text",
            "photo",
            "media.ocr_text",
        ),
        filters=RichFilters(
            captured_from=datetime(
                2026,
                8,
                15,
                8,
                tzinfo=timezone(timedelta(hours=8)),
            ),
            captured_to=NOW + timedelta(days=1),
        ),
        limit=10,
    )

    assert [hit.resource for hit in result.hits] == [at_from, before_to]
    assert all(
        "media.captured_at" in hit.matched_predicates
        for hit in result.hits
    )
    assert all(hit.captured_at is not None for hit in result.hits)
    assert missing not in [hit.resource for hit in result.hits]


def test_file_modified_range_is_utc_half_open_and_missing_excludes() -> None:
    at_from = _summary("from.pdf")
    before_to = _summary("before-to.pdf")
    at_to = _summary("to.pdf")
    missing = _summary("missing.pdf")
    candidates = tuple(
        RichCandidate(resource, index)
        for index, resource in enumerate(
            (at_from, before_to, at_to, missing),
            start=1,
        )
    )
    repository = StubRichRepository(
        candidates=candidates,
        signals={
            at_from.resource_ref: _signals(
                at_from,
                file_modified_at=NOW,
            ),
            before_to.resource_ref: _signals(
                before_to,
                file_modified_at=NOW + timedelta(hours=23),
            ),
            at_to.resource_ref: _signals(
                at_to,
                file_modified_at=NOW + timedelta(days=1),
            ),
            missing.resource_ref: _signals(missing),
        },
    )

    result = RichRetrievalService(repository).retrieve_resources(
        primary=ObservationTextPrimary(
            "observation_text",
            "machine learning",
            "document.text_excerpt",
        ),
        filters=RichFilters(
            file_modified_from=datetime(
                2026,
                8,
                15,
                8,
                tzinfo=timezone(timedelta(hours=8)),
            ),
            file_modified_to=datetime(
                2026,
                8,
                15,
                16,
                tzinfo=timezone(-timedelta(hours=8)),
            ),
        ),
    )

    assert [hit.resource for hit in result.hits] == [at_from, before_to]
    assert [hit.file_modified_at for hit in result.hits] == [
        NOW,
        NOW + timedelta(hours=23),
    ]
    assert all(
        hit.matched_predicates == (
            "file.modified_at",
        )
        for hit in result.hits
    )
    assert [stage.stage for stage in result.stages] == [
        "observation_text_primary",
        "file_modified_at_filter",
        "final_limit",
    ]
    requested = repository.filter_calls[0][1]
    assert requested.file_modified_from == NOW
    assert requested.file_modified_to == NOW + timedelta(days=1)


def test_file_modified_only_from_and_only_to_preserve_rank() -> None:
    earlier = _summary("earlier.pdf")
    later = _summary("later.pdf")
    candidates = (
        RichCandidate(earlier, 2),
        RichCandidate(later, 7),
    )
    signals = {
        earlier.resource_ref: _signals(
            earlier,
            file_modified_at=NOW,
        ),
        later.resource_ref: _signals(
            later,
            file_modified_at=NOW + timedelta(days=2),
        ),
    }

    only_from = RichRetrievalService(StubRichRepository(
        candidates=candidates,
        signals=signals,
    )).retrieve_resources(
        primary=ObservationTextPrimary(
            "observation_text",
            "document",
            "document.text_excerpt",
        ),
        filters=RichFilters(
            file_modified_from=NOW + timedelta(days=1),
        ),
    )
    only_to = RichRetrievalService(StubRichRepository(
        candidates=candidates,
        signals=signals,
    )).retrieve_resources(
        primary=ObservationTextPrimary(
            "observation_text",
            "document",
            "document.text_excerpt",
        ),
        filters=RichFilters(
            file_modified_to=NOW + timedelta(days=1),
        ),
    )

    assert [hit.source_rank for hit in only_from.hits] == [7]
    assert [hit.source_rank for hit in only_to.hits] == [2]


@pytest.mark.parametrize(
    "filters",
    [
        RichFilters(captured_from=datetime(2026, 1, 1)),
        RichFilters(file_modified_from=datetime(2026, 1, 1)),
        RichFilters(file_modified_to=datetime(2026, 1, 1)),
        RichFilters(
            captured_from=NOW,
            captured_to=NOW,
        ),
        RichFilters(
            file_modified_from=NOW,
            file_modified_to=NOW,
        ),
        RichFilters(
            file_modified_from=NOW + timedelta(seconds=1),
            file_modified_to=NOW,
        ),
        RichFilters(required_predicates=("unknown.predicate",)),
        RichFilters(mime_type="image/jpeg", mime_category="image"),
        RichFilters(mime_category="image/jpeg"),
        RichFilters(resource_type="album"),
    ],
)
def test_filter_validation(filters) -> None:
    with pytest.raises(InvalidQueryError):
        RichRetrievalService(StubRichRepository()).retrieve_resources(
            primary=ObservationTextPrimary(
                "observation_text",
                "text",
                "document.text_excerpt",
            ),
            filters=filters,
        )


def test_required_predicates_are_batch_filtered_and_reported() -> None:
    included = _summary("included.jpg")
    excluded = _summary("excluded.jpg")
    candidates = (
        RichCandidate(included, 2, ("media.ocr_text",)),
        RichCandidate(excluded, 5, ("media.ocr_text",)),
    )
    repository = StubRichRepository(
        candidates=candidates,
        signals={
            included.resource_ref: _signals(
                included,
                predicates=frozenset({
                    "media.ocr_text",
                    "media.camera_make",
                }),
            ),
            excluded.resource_ref: _signals(
                excluded,
                predicates=frozenset({"media.ocr_text"}),
            ),
        },
    )
    result = RichRetrievalService(repository).retrieve_resources(
        primary=ObservationTextPrimary(
            "observation_text",
            "CAMBRIDGE",
            "media.ocr_text",
        ),
        filters=RichFilters(
            required_predicates=("media.camera_make",),
        ),
    )

    assert [hit.source_rank for hit in result.hits] == [2]
    assert result.hits[0].matched_predicates == (
        "media.ocr_text",
        "media.camera_make",
    )
    assert repository.search_calls[0][1] == 50
    assert len(repository.filter_calls) == 1


def test_required_captured_at_returns_the_batched_structured_signal() -> None:
    included = _summary("dated.jpg")
    missing = _summary("undated.jpg")
    repository = StubRichRepository(
        candidates=(
            RichCandidate(included, 1, ("media.ocr_text",)),
            RichCandidate(missing, 2, ("media.ocr_text",)),
        ),
        signals={
            included.resource_ref: _signals(
                included,
                captured_at=NOW,
                predicates=frozenset({"media.captured_at"}),
            ),
            missing.resource_ref: _signals(missing),
        },
    )

    result = RichRetrievalService(repository).retrieve_resources(
        primary=ObservationTextPrimary(
            "observation_text",
            "car",
            "media.ocr_text",
        ),
        filters=RichFilters(
            required_predicates=("media.captured_at",),
        ),
    )

    assert len(result.hits) == 1
    assert result.hits[0].captured_at == NOW
    assert result.hits[0].matched_predicates == (
        "media.ocr_text",
        "media.captured_at",
    )


def test_file_modified_required_only_returns_signal_without_duplicates() -> None:
    resource = _summary("document.pdf")
    candidate = RichCandidate(
        resource,
        3,
        ("document.text_excerpt",),
    )
    repository = StubRichRepository(
        candidates=(candidate,),
        signals={
            resource.resource_ref: _signals(
                resource,
                file_modified_at=NOW,
                predicates=frozenset({"file.modified_at"}),
            ),
        },
    )

    result = RichRetrievalService(repository).retrieve_resources(
        primary=ObservationTextPrimary(
            "observation_text",
            "machine learning",
            "document.text_excerpt",
        ),
        filters=RichFilters(
            file_modified_from=NOW,
            required_predicates=("file.modified_at",),
        ),
    )

    assert result.hits[0].file_modified_at == NOW
    assert result.hits[0].matched_predicates == (
        "document.text_excerpt",
        "file.modified_at",
    )


def test_captured_and_file_modified_use_strict_and_semantics() -> None:
    included = _summary("included.jpg")
    wrong_capture = _summary("wrong-capture.jpg")
    wrong_modified = _summary("wrong-modified.jpg")
    candidates = tuple(
        RichCandidate(resource, rank)
        for rank, resource in enumerate(
            (included, wrong_capture, wrong_modified),
            start=1,
        )
    )
    repository = StubRichRepository(
        candidates=candidates,
        signals={
            included.resource_ref: _signals(
                included,
                captured_at=NOW,
                file_modified_at=NOW,
            ),
            wrong_capture.resource_ref: _signals(
                wrong_capture,
                captured_at=NOW - timedelta(days=1),
                file_modified_at=NOW,
            ),
            wrong_modified.resource_ref: _signals(
                wrong_modified,
                captured_at=NOW,
                file_modified_at=NOW - timedelta(days=1),
            ),
        },
    )

    result = RichRetrievalService(repository).retrieve_resources(
        primary=ObservationTextPrimary(
            "observation_text",
            "Cambridge",
            "media.ocr_text",
        ),
        filters=RichFilters(
            captured_from=NOW,
            file_modified_from=NOW,
        ),
    )

    assert [hit.resource for hit in result.hits] == [included]
    assert result.hits[0].captured_at == NOW
    assert result.hits[0].file_modified_at == NOW
    assert result.hits[0].matched_predicates == (
        "media.captured_at",
        "file.modified_at",
    )


def test_file_modified_signal_is_not_requested_unconditionally() -> None:
    resource = _summary("document.pdf")
    repository = StubRichRepository(
        candidates=(RichCandidate(resource, 1),),
    )

    result = RichRetrievalService(repository).retrieve_resources(
        primary=ObservationTextPrimary(
            "observation_text",
            "machine learning",
            "document.text_excerpt",
        ),
    )

    assert result.hits[0].file_modified_at is None
    assert repository.filter_calls == []


def test_zero_hits_is_success_and_repository_failure_aborts() -> None:
    primary = ObservationTextPrimary(
        "observation_text",
        "none",
        "document.text_excerpt",
    )
    result = RichRetrievalService(
        StubRichRepository()
    ).retrieve_resources(primary=primary)
    assert result.hits == ()
    assert result.stages[-1].output_count == 0

    class FailingRepository(StubRichRepository):
        def search_current_observation_text(self, *, primary, limit):
            raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        RichRetrievalService(FailingRepository()).retrieve_resources(
            primary=primary
        )


def test_provider_failure_aborts_whole_request() -> None:
    class FailingRetrievalService:
        def retrieve_resources(self, **kwargs):
            raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        RichRetrievalService(
            StubRichRepository(),
            FailingRetrievalService(),
        ).retrieve_resources(
            primary=ProviderSemanticPrimary(
                "provider_semantic",
                "car",
                "immich",
            )
        )
