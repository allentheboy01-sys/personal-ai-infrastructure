from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Callable, Mapping
from urllib.parse import urlsplit

from pdi.query import InvalidQueryError, QueryService, ResourceSummary
from pdi.query.cursor import decode_cursor, encode_cursor, query_fingerprint
from pdi.rich_retrieval import (
    ObservationTextPrimary as RichObservationTextPrimary,
    PersonLabelPrimary as RichPersonLabelPrimary,
    ProviderSemanticPrimary as RichProviderSemanticPrimary,
    RichFilters,
    RichFilterSignals,
    RichRetrievalService,
)
from pdi.retrieval import ProviderCapabilityUnavailableError

from .errors import (
    InvalidResourceQueryContinuationError,
    InvalidResourceQueryFiltersError,
    InvalidResourceQueryPrimaryError,
    InvalidResourceQuerySortError,
    ResourceQueryProjectionError,
)
from .models import (
    CompactResource,
    MetadataTextPrimary,
    ObservationTextPrimary,
    PathTreePrimary,
    PersonLabelPrimary,
    ProviderSemanticPrimary,
    RecentPrimary,
    ResourceQueryFilters,
    ResourceQueryPrimary,
    ResourceQueryResult,
    ResourceQuerySort,
)
from .serialization import serialized_result_bytes


RESOURCE_LIST_SCHEMA = "pdi.resource-list.v1"
DEFAULT_RESOURCE_QUERY_LIMIT = 10
MAX_RESOURCE_QUERY_LIMIT = 50
DEFAULT_RESOURCE_SCAN_LIMIT = 500
MAX_RESOURCE_SCAN_LIMIT = 2000
RESOURCE_QUERY_TIMEOUT_SECONDS = 30.0
STRUCTURED_RESULT_MAX_BYTES = 64 * 1024
MODEL_PROJECTION_TARGET_BYTES = 8 * 1024

_PAGE_LIMIT = 100
_PROVIDER_SEMANTIC_CANDIDATE_LIMIT = 100
_CONTINUATION_OPERATION = "unified_resource_query"
_MAX_TITLE_BYTES = 512
_MAX_PROVIDER_BYTES = 128
_MAX_RELATIVE_PATH_BYTES = 1024


@dataclass(frozen=True, slots=True)
class _Candidate:
    resource: ResourceSummary
    source_rank: int
    match_basis: str
    captured_at: datetime | None = None
    file_modified_at: datetime | None = None
    relative_path: str | None = None


@dataclass(frozen=True, slots=True)
class _Selection:
    candidates: tuple[_Candidate, ...]
    scanned_count: int
    source_has_more: bool
    timed_out: bool


class ResourceQueryService:
    """One deterministic, bounded public selection over existing read services."""

    def __init__(
        self,
        query_service: QueryService,
        rich_retrieval_service: RichRetrievalService | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self._query = query_service
        self._rich = rich_retrieval_service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._monotonic = monotonic_clock or monotonic

    def query_resources(
        self,
        *,
        primary: ResourceQueryPrimary,
        filters: ResourceQueryFilters | None = None,
        sort: ResourceQuerySort | None = None,
        limit: int = DEFAULT_RESOURCE_QUERY_LIMIT,
        scan_limit: int = DEFAULT_RESOURCE_SCAN_LIMIT,
        continuable: bool = False,
        continuation: str | None = None,
    ) -> ResourceQueryResult:
        primary = self._validate_primary(primary)
        filters = self._validate_filters(filters or ResourceQueryFilters())
        self._validate_primary_filter_combination(primary, filters)
        if isinstance(primary, PathTreePrimary):
            if (
                filters.path_prefix is not None
                and filters.path_prefix != primary.path_prefix
            ):
                raise InvalidResourceQueryFiltersError(
                    "path_tree primary and filter path_prefix must match"
                )
            filters = replace(filters, path_prefix=primary.path_prefix)
        sort = self._validate_sort(primary, sort)
        limit = self._bounded_integer(
            limit,
            "limit",
            MAX_RESOURCE_QUERY_LIMIT,
        )
        scan_limit = self._bounded_integer(
            scan_limit,
            "scan_limit",
            MAX_RESOURCE_SCAN_LIMIT,
        )
        if not isinstance(continuable, bool):
            raise InvalidResourceQueryContinuationError(
                "continuable must be a boolean"
            )
        if continuation is not None and not continuable:
            raise InvalidResourceQueryContinuationError(
                "continuation requires continuable=true"
            )

        identity = self._identity(primary, filters, sort)
        fingerprint = query_fingerprint(identity)
        offset, snapshot = self._continuation_state(
            continuation,
            fingerprint=fingerprint,
        )
        if snapshot is None:
            snapshot = self._utc(self._clock(), "clock")
        execution_filters = replace(
            filters,
            observed_to=min(filters.observed_to or snapshot, snapshot),
        )
        started_at = self._monotonic()

        if isinstance(
            primary,
            (RecentPrimary, MetadataTextPrimary, PathTreePrimary),
        ):
            selection = self._select_query_candidates(
                primary=primary,
                filters=execution_filters,
                sort=sort,
                snapshot=snapshot,
                scan_limit=scan_limit,
                started_at=started_at,
            )
        else:
            selection = self._select_rich_candidates(
                primary=primary,
                filters=execution_filters,
                sort=sort,
                scan_limit=scan_limit,
                started_at=started_at,
            )

        candidates = self._apply_signal_filters(
            selection.candidates,
            filters=execution_filters,
            sort=sort,
        )
        candidates = self._sort_candidates(
            candidates,
            primary=primary,
            sort=sort,
        )

        partial_reason = self._partial_reason(
            selection,
            primary=primary,
            sort=sort,
        )
        page = candidates[offset:offset + limit]
        resources = tuple(
            self._compact_resource(
                candidate,
                filters=execution_filters,
                sort=sort,
                rank=offset + index,
            )
            for index, candidate in enumerate(page, start=1)
        )
        continuation_value = self._next_continuation(
            continuable=continuable,
            fingerprint=fingerprint,
            snapshot=snapshot,
            next_offset=offset + len(resources),
            buffered_more=offset + len(resources) < len(candidates),
            source_has_more=(
                selection.source_has_more and partial_reason is None
            ),
        )
        result = ResourceQueryResult(
            schema=RESOURCE_LIST_SCHEMA,
            query_kind=primary.kind,
            snapshot=snapshot,
            selection_status=(
                "bounded_partial"
                if partial_reason is not None
                else "complete"
            ),
            bound_reason=partial_reason,
            scanned_count=selection.scanned_count,
            resources=resources,
            continuation=continuation_value,
        )
        return self._enforce_serialized_bound(
            result,
            continuable=continuable,
            fingerprint=fingerprint,
            snapshot=snapshot,
            offset=offset,
        )

    def _select_query_candidates(
        self,
        *,
        primary: RecentPrimary | MetadataTextPrimary | PathTreePrimary,
        filters: ResourceQueryFilters,
        sort: ResourceQuerySort,
        snapshot: datetime,
        scan_limit: int,
        started_at: float,
    ) -> _Selection:
        observed_from = filters.observed_from
        observed_to = min(filters.observed_to or snapshot, snapshot)
        if isinstance(primary, RecentPrimary) and observed_from is None:
            observed_from = snapshot - timedelta(days=30)
        path_prefix = (
            primary.path_prefix
            if isinstance(primary, PathTreePrimary)
            else filters.path_prefix
        )

        resources: list[ResourceSummary] = []
        cursor: str | None = None
        source_has_more = False
        timed_out = False
        while len(resources) < scan_limit:
            if self._expired(started_at):
                timed_out = True
                break
            page_limit = min(_PAGE_LIMIT, scan_limit - len(resources))
            try:
                if isinstance(primary, MetadataTextPrimary):
                    page = self._query.search_resource_page(
                        query=primary.query,
                        observed_from=observed_from,
                        observed_to=observed_to,
                        provider=filters.provider,
                        resource_type=filters.resource_type,
                        mime_type=filters.mime_type,
                        mime_category=filters.mime_category,
                        path_prefix=path_prefix,
                        limit=page_limit,
                        cursor=cursor,
                    )
                else:
                    page = self._query.list_resource_page(
                        observed_from=observed_from,
                        observed_to=observed_to,
                        provider=filters.provider,
                        resource_type=filters.resource_type,
                        mime_type=filters.mime_type,
                        mime_category=filters.mime_category,
                        path_prefix=path_prefix,
                        limit=page_limit,
                        cursor=cursor,
                    )
            except InvalidQueryError as error:
                raise InvalidResourceQueryFiltersError(str(error)) from error
            resources.extend(page.resources)
            cursor = page.next_cursor
            source_has_more = cursor is not None
            if cursor is None or not page.resources:
                break
        if self._expired(started_at):
            timed_out = True

        candidates = tuple(
            self._query_candidate(resource, primary, filters, sort)
            for resource in resources
        )
        return _Selection(
            candidates=candidates,
            scanned_count=len(resources),
            source_has_more=source_has_more,
            timed_out=timed_out,
        )

    def _select_rich_candidates(
        self,
        *,
        primary: (
            ProviderSemanticPrimary
            | ObservationTextPrimary
            | PersonLabelPrimary
        ),
        filters: ResourceQueryFilters,
        sort: ResourceQuerySort,
        scan_limit: int,
        started_at: float,
    ) -> _Selection:
        rich = self._require_rich()
        if isinstance(primary, ProviderSemanticPrimary):
            candidate_limit = min(
                scan_limit,
                _PROVIDER_SEMANTIC_CANDIDATE_LIMIT,
            )
            rich_primary = RichProviderSemanticPrimary(
                kind="provider_semantic",
                query=primary.query,
                provider="immich",
            )
        elif isinstance(primary, ObservationTextPrimary):
            candidate_limit = scan_limit
            rich_primary = RichObservationTextPrimary(
                kind="observation_text",
                query=primary.query,
                predicate=primary.predicate,
            )
        else:
            candidate_limit = scan_limit
            rich_primary = RichPersonLabelPrimary(
                kind="person_label",
                label=primary.label,
                provider=primary.provider,
            )

        rich_filters = self._rich_filters(filters, sort=sort)
        try:
            result = rich.select_resources(
                primary=rich_primary,
                filters=rich_filters,
                candidate_limit=candidate_limit,
            )
        except InvalidQueryError as error:
            raise InvalidResourceQueryFiltersError(str(error)) from error
        timed_out = self._expired(started_at)
        primary_count = (
            result.stages[0].output_count + result.unmapped_hit_count
        )
        candidates = tuple(
            _Candidate(
                resource=hit.resource,
                source_rank=hit.source_rank,
                match_basis=primary.kind,
                captured_at=hit.captured_at,
                file_modified_at=hit.file_modified_at,
                relative_path=(
                    self._selected_relative_path(
                        hit.resource,
                        filters=filters,
                        path_prefix=filters.path_prefix,
                    )
                    if sort.basis == "path"
                    else None
                ),
            )
            for hit in result.hits
        )
        return _Selection(
            candidates=candidates,
            scanned_count=primary_count,
            source_has_more=primary_count >= candidate_limit,
            timed_out=timed_out,
        )

    def _apply_signal_filters(
        self,
        candidates: tuple[_Candidate, ...],
        *,
        filters: ResourceQueryFilters,
        sort: ResourceQuerySort,
    ) -> tuple[_Candidate, ...]:
        candidates = tuple(
            candidate
            for candidate in candidates
            if self._time_matches(
                candidate.resource.pdi_first_observed_at,
                filters.observed_from,
                filters.observed_to,
            )
        )
        needs_signals = any((
            filters.captured_from,
            filters.captured_to,
            filters.file_modified_from,
            filters.file_modified_to,
            filters.required_predicates,
            sort.basis in {"captured_at", "file_modified_at"},
        ))
        if not candidates or not needs_signals:
            return candidates

        missing = tuple(
            candidate.resource.resource_ref
            for candidate in candidates
        )
        signals: Mapping[str, RichFilterSignals] = {}
        if missing:
            rich = self._require_rich()
            try:
                signals = rich.load_filter_signals(
                    resource_refs=missing,
                    filters=self._rich_filters(
                        filters,
                        sort=sort,
                        include_source_filters=False,
                    ),
                )
            except InvalidQueryError as error:
                raise InvalidResourceQueryFiltersError(str(error)) from error

        selected: list[_Candidate] = []
        required = set(filters.required_predicates)
        for candidate in candidates:
            signal = signals.get(candidate.resource.resource_ref)
            captured_at = candidate.captured_at
            file_modified_at = candidate.file_modified_at
            current_predicates: frozenset[str] = frozenset()
            if signal is not None:
                captured_at = getattr(signal, "captured_at")
                file_modified_at = getattr(signal, "file_modified_at")
                current_predicates = getattr(signal, "current_predicates")
            elif required:
                # Rich selection already enforced required predicates.
                current_predicates = frozenset(required)
            if not required.issubset(current_predicates):
                continue
            if not self._time_matches(
                captured_at,
                filters.captured_from,
                filters.captured_to,
            ):
                continue
            if not self._time_matches(
                file_modified_at,
                filters.file_modified_from,
                filters.file_modified_to,
            ):
                continue
            if sort.basis == "captured_at" and captured_at is None:
                continue
            if sort.basis == "file_modified_at" and file_modified_at is None:
                continue
            selected.append(replace(
                candidate,
                captured_at=captured_at,
                file_modified_at=file_modified_at,
            ))
        return tuple(selected)

    def _query_candidate(
        self,
        resource: ResourceSummary,
        primary: RecentPrimary | MetadataTextPrimary | PathTreePrimary,
        filters: ResourceQueryFilters,
        sort: ResourceQuerySort,
    ) -> _Candidate:
        if isinstance(primary, MetadataTextPrimary):
            score, basis, relative_path = self._metadata_match(
                resource,
                primary.query,
                filters,
            )
            if (
                relative_path is None
                and (
                    sort.basis == "path"
                    or filters.path_prefix is not None
                )
            ):
                relative_path = self._selected_relative_path(
                    resource,
                    filters=filters,
                    path_prefix=filters.path_prefix,
                )
            return _Candidate(
                resource=resource,
                source_rank=score,
                match_basis=basis,
                relative_path=relative_path,
            )
        if isinstance(primary, PathTreePrimary):
            relative_path = self._selected_relative_path(
                resource,
                filters=filters,
                path_prefix=primary.path_prefix,
            )
            if relative_path is None:
                raise ResourceQueryProjectionError(
                    "path_tree Resource has no safe provider-relative path"
                )
            return _Candidate(
                resource=resource,
                source_rank=0,
                match_basis="path_prefix",
                relative_path=relative_path,
            )
        return _Candidate(
            resource=resource,
            source_rank=0,
            match_basis="recent",
            relative_path=(
                self._selected_relative_path(
                    resource,
                    filters=filters,
                    path_prefix=filters.path_prefix,
                )
                if filters.path_prefix is not None
                else None
            ),
        )

    def _metadata_match(
        self,
        resource: ResourceSummary,
        query: str,
        filters: ResourceQueryFilters,
    ) -> tuple[int, str, str | None]:
        needle = query.casefold()
        names = [resource.display_name]
        paths: list[str] = []
        for source in self._eligible_sources(resource, filters):
            if source.name:
                names.append(source.name)
            path = self._safe_relative_path(source.location)
            if path is not None:
                paths.append(path)
                names.append(path.rsplit("/", 1)[-1])
        folded_names = [name.casefold() for name in names]
        if any(name == needle for name in folded_names):
            return 0, "title_exact", None
        if any(name.startswith(needle) for name in folded_names):
            return 1, "title_prefix", None
        if any(needle in name for name in folded_names):
            return 2, "title_substring", None
        matching_paths = sorted(
            path for path in paths if needle in path.casefold()
        )
        if matching_paths:
            return 3, "path_substring", matching_paths[0]
        raise ResourceQueryProjectionError(
            "metadata_text Resource has no reproducible public match"
        )

    def _sort_candidates(
        self,
        candidates: tuple[_Candidate, ...],
        *,
        primary: ResourceQueryPrimary,
        sort: ResourceQuerySort,
    ) -> tuple[_Candidate, ...]:
        ordered = sorted(
            candidates,
            key=lambda candidate: candidate.resource.resource_ref,
        )
        if sort.basis == "relevance":
            ordered.sort(
                key=lambda candidate: candidate.resource.pdi_first_observed_at,
                reverse=True,
            )
            ordered.sort(key=lambda candidate: candidate.source_rank)
        elif sort.basis == "path":
            ordered = [
                candidate
                for candidate in ordered
                if candidate.relative_path is not None
            ]
            ordered.sort(
                key=lambda candidate: candidate.relative_path.casefold(),
                reverse=sort.direction == "desc",
            )
        else:
            attribute = {
                "pdi_observed_at": "pdi_first_observed_at",
                "captured_at": "captured_at",
                "file_modified_at": "file_modified_at",
            }[sort.basis]
            if attribute == "pdi_first_observed_at":
                key = lambda candidate: candidate.resource.pdi_first_observed_at
            else:
                key = lambda candidate: getattr(candidate, attribute)
            ordered.sort(key=key, reverse=sort.direction == "desc")
        return tuple(ordered)

    def _compact_resource(
        self,
        candidate: _Candidate,
        *,
        filters: ResourceQueryFilters,
        sort: ResourceQuerySort,
        rank: int,
    ) -> CompactResource:
        sources = self._eligible_sources(candidate.resource, filters)
        providers = tuple(sorted({
            self._bounded_text(source.provider, _MAX_PROVIDER_BYTES)
            for source in sources
        }))
        mime_types = {
            source.mime_type.lower()
            for source in sources
            if source.mime_type
        }
        mime_type = next(iter(mime_types)) if len(mime_types) == 1 else None
        categories = {self._mime_category(value) for value in mime_types}
        mime_category = (
            next(iter(categories)) if len(categories) == 1 else None
        )
        if sort.basis == "captured_at":
            relevant_time = candidate.captured_at
            time_basis = "media.captured_at"
        elif sort.basis == "file_modified_at":
            relevant_time = candidate.file_modified_at
            time_basis = "file.modified_at"
        else:
            relevant_time = candidate.resource.pdi_first_observed_at
            time_basis = "pdi_first_observed_at"
        return CompactResource(
            resource_ref=candidate.resource.resource_ref,
            title=self._bounded_text(
                candidate.resource.display_name,
                _MAX_TITLE_BYTES,
            ),
            resource_type=candidate.resource.resource_type,
            mime_type=mime_type,
            mime_category=mime_category,
            providers=providers,
            relevant_time=relevant_time,
            time_basis=time_basis,
            rank=rank,
            match_basis=candidate.match_basis,
            relative_path=candidate.relative_path,
        )

    def _partial_reason(
        self,
        selection: _Selection,
        *,
        primary: ResourceQueryPrimary,
        sort: ResourceQuerySort,
    ) -> str | None:
        if selection.timed_out:
            return "timeout"
        if not selection.source_has_more:
            return None
        if isinstance(primary, ProviderSemanticPrimary):
            return None if sort.basis == "relevance" else "scan_limit"
        return "scan_limit"

    def _enforce_serialized_bound(
        self,
        result: ResourceQueryResult,
        *,
        continuable: bool,
        fingerprint: str,
        snapshot: datetime,
        offset: int,
    ) -> ResourceQueryResult:
        bounded = result
        resources = list(result.resources)
        while serialized_result_bytes(bounded) > STRUCTURED_RESULT_MAX_BYTES:
            if not resources:
                raise ResourceQueryProjectionError(
                    "Resource query envelope exceeds the byte limit"
                )
            resources.pop()
            continuation = self._next_continuation(
                continuable=continuable,
                fingerprint=fingerprint,
                snapshot=snapshot,
                next_offset=offset + len(resources),
                buffered_more=True,
                source_has_more=False,
            )
            bounded = replace(
                result,
                selection_status="bounded_partial",
                bound_reason="serialized_byte_limit",
                resources=tuple(resources),
                continuation=continuation,
            )
        return bounded

    def _validate_primary(
        self,
        primary: ResourceQueryPrimary,
    ) -> ResourceQueryPrimary:
        supported = (
            RecentPrimary,
            MetadataTextPrimary,
            ProviderSemanticPrimary,
            ObservationTextPrimary,
            PersonLabelPrimary,
            PathTreePrimary,
        )
        if not isinstance(primary, supported):
            raise InvalidResourceQueryPrimaryError(
                "exactly one supported typed primary is required"
            )
        if isinstance(primary, (MetadataTextPrimary, ProviderSemanticPrimary, ObservationTextPrimary)):
            self._required_text(primary.query, "primary query")
        if isinstance(primary, ProviderSemanticPrimary):
            if primary.provider != "immich":
                raise ProviderCapabilityUnavailableError(
                    "provider_semantic currently requires provider=immich"
                )
        if isinstance(primary, PersonLabelPrimary):
            self._required_text(primary.label, "person label")
        if isinstance(primary, PathTreePrimary):
            self._required_text(primary.path_prefix, "path_prefix")
        return primary

    def _validate_filters(
        self,
        filters: ResourceQueryFilters,
    ) -> ResourceQueryFilters:
        if not isinstance(filters, ResourceQueryFilters):
            raise InvalidResourceQueryFiltersError(
                "filters must use the typed Resource query contract"
            )
        if filters.mime_type is not None and filters.mime_category is not None:
            raise InvalidResourceQueryFiltersError(
                "mime_type and mime_category cannot be combined"
            )
        for name in (
            "observed_from",
            "observed_to",
            "captured_from",
            "captured_to",
            "file_modified_from",
            "file_modified_to",
        ):
            value = getattr(filters, name)
            if value is not None:
                self._utc(value, name)
        for prefix in ("observed", "captured", "file_modified"):
            lower = getattr(filters, f"{prefix}_from")
            upper = getattr(filters, f"{prefix}_to")
            if lower is not None and upper is not None:
                if self._utc(lower, f"{prefix}_from") >= self._utc(
                    upper,
                    f"{prefix}_to",
                ):
                    raise InvalidResourceQueryFiltersError(
                        f"{prefix}_from must be earlier than {prefix}_to"
                    )
        return replace(
            filters,
            observed_from=self._utc_or_none(
                filters.observed_from,
                "observed_from",
            ),
            observed_to=self._utc_or_none(filters.observed_to, "observed_to"),
            captured_from=self._utc_or_none(
                filters.captured_from,
                "captured_from",
            ),
            captured_to=self._utc_or_none(filters.captured_to, "captured_to"),
            file_modified_from=self._utc_or_none(
                filters.file_modified_from,
                "file_modified_from",
            ),
            file_modified_to=self._utc_or_none(
                filters.file_modified_to,
                "file_modified_to",
            ),
        )

    @staticmethod
    def _validate_primary_filter_combination(
        primary: ResourceQueryPrimary,
        filters: ResourceQueryFilters,
    ) -> None:
        primary_provider = getattr(primary, "provider", None)
        if (
            primary_provider is not None
            and filters.provider is not None
            and primary_provider != filters.provider
        ):
            raise InvalidResourceQueryFiltersError(
                "primary provider and filter provider must match"
            )

    def _validate_sort(
        self,
        primary: ResourceQueryPrimary,
        sort: ResourceQuerySort | None,
    ) -> ResourceQuerySort:
        defaults = {
            "recent": ResourceQuerySort("pdi_observed_at", "desc"),
            "metadata_text": ResourceQuerySort("relevance", "desc"),
            "provider_semantic": ResourceQuerySort("relevance", "desc"),
            "observation_text": ResourceQuerySort("relevance", "desc"),
            "person_label": ResourceQuerySort("relevance", "desc"),
            "path_tree": ResourceQuerySort("path", "asc"),
        }
        sort = sort or defaults[primary.kind]
        allowed = {
            "recent": {"pdi_observed_at", "captured_at", "file_modified_at"},
            "metadata_text": {"relevance", "pdi_observed_at", "captured_at", "file_modified_at", "path"},
            "provider_semantic": {"relevance"},
            "observation_text": {"relevance", "pdi_observed_at", "captured_at", "file_modified_at", "path"},
            "person_label": {"relevance", "pdi_observed_at", "captured_at", "file_modified_at"},
            "path_tree": {"path", "pdi_observed_at", "captured_at", "file_modified_at"},
        }
        if sort.basis not in allowed[primary.kind]:
            raise InvalidResourceQuerySortError(
                f"sort basis {sort.basis} is not supported for {primary.kind}"
            )
        direction = sort.direction
        if direction is None:
            direction = "asc" if sort.basis == "path" else "desc"
        if sort.basis == "relevance" and direction != "desc":
            raise InvalidResourceQuerySortError(
                "relevance sort supports only direction=desc"
            )
        return ResourceQuerySort(sort.basis, direction)

    def _continuation_state(
        self,
        continuation: str | None,
        *,
        fingerprint: str,
    ) -> tuple[int, datetime | None]:
        if continuation is None:
            return 0, None
        try:
            payload = decode_cursor(continuation)
        except InvalidQueryError as error:
            raise InvalidResourceQueryContinuationError(str(error)) from error
        if payload.get("operation") != _CONTINUATION_OPERATION:
            raise InvalidResourceQueryContinuationError(
                "continuation does not belong to resource query"
            )
        if payload.get("fingerprint") != fingerprint:
            raise InvalidResourceQueryContinuationError(
                "continuation does not match the query"
            )
        position = payload.get("position")
        if not isinstance(position, dict):
            raise InvalidResourceQueryContinuationError(
                "continuation is malformed"
            )
        offset = position.get("offset")
        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or not 0 <= offset <= MAX_RESOURCE_SCAN_LIMIT
        ):
            raise InvalidResourceQueryContinuationError(
                "continuation is malformed"
            )
        snapshot_value = payload.get("snapshot")
        if not isinstance(snapshot_value, str):
            raise InvalidResourceQueryContinuationError(
                "continuation is malformed"
            )
        try:
            snapshot = self._utc(
                datetime.fromisoformat(snapshot_value),
                "snapshot",
            )
        except (ValueError, InvalidResourceQueryFiltersError) as error:
            raise InvalidResourceQueryContinuationError(
                "continuation is malformed"
            ) from error
        return offset, snapshot

    @staticmethod
    def _next_continuation(
        *,
        continuable: bool,
        fingerprint: str,
        snapshot: datetime,
        next_offset: int,
        buffered_more: bool,
        source_has_more: bool,
    ) -> str | None:
        if not continuable or not (buffered_more or source_has_more):
            return None
        return encode_cursor({
            "operation": _CONTINUATION_OPERATION,
            "fingerprint": fingerprint,
            "snapshot": snapshot.isoformat(),
            "position": {"offset": next_offset},
        })

    @staticmethod
    def _identity(
        primary: ResourceQueryPrimary,
        filters: ResourceQueryFilters,
        sort: ResourceQuerySort,
    ) -> dict[str, object]:
        primary_values = {
            field: getattr(primary, field)
            for field in primary.__dataclass_fields__
        }
        filter_values = {
            field: (
                value.isoformat()
                if isinstance(value, datetime)
                else list(value)
                if isinstance(value, tuple)
                else value
            )
            for field in filters.__dataclass_fields__
            if (value := getattr(filters, field)) is not None
        }
        return {
            "schema": RESOURCE_LIST_SCHEMA,
            "primary": primary_values,
            "filters": filter_values,
            "sort": {
                "basis": sort.basis,
                "direction": sort.direction,
            },
        }

    def _rich_filters(
        self,
        filters: ResourceQueryFilters,
        *,
        sort: ResourceQuerySort,
        include_source_filters: bool = True,
    ) -> RichFilters:
        required = list(filters.required_predicates)
        if sort.basis == "captured_at" and "media.captured_at" not in required:
            required.append("media.captured_at")
        if sort.basis == "file_modified_at" and "file.modified_at" not in required:
            required.append("file.modified_at")
        return RichFilters(
            provider=(filters.provider if include_source_filters else None),
            resource_type=(
                filters.resource_type if include_source_filters else None
            ),
            mime_type=(filters.mime_type if include_source_filters else None),
            mime_category=(
                filters.mime_category if include_source_filters else None
            ),
            path_prefix=(
                filters.path_prefix if include_source_filters else None
            ),
            captured_from=filters.captured_from,
            captured_to=filters.captured_to,
            file_modified_from=filters.file_modified_from,
            file_modified_to=filters.file_modified_to,
            required_predicates=tuple(required),
        )

    def _eligible_sources(
        self,
        resource: ResourceSummary,
        filters: ResourceQueryFilters,
    ):
        sources = []
        for source in resource.sources:
            if not source.is_active:
                continue
            if (
                filters.provider is not None
                and source.provider != filters.provider
            ):
                continue
            if (
                filters.mime_type is not None
                and source.mime_type != filters.mime_type
            ):
                continue
            if filters.mime_category is not None:
                if (
                    self._mime_category(source.mime_type)
                    != filters.mime_category.lower()
                ):
                    continue
            if filters.path_prefix is not None:
                path = source.location
                if path is None or not path.startswith(filters.path_prefix):
                    continue
            sources.append(source)
        return tuple(sources)

    def _selected_relative_path(
        self,
        resource: ResourceSummary,
        *,
        filters: ResourceQueryFilters,
        path_prefix: str | None,
    ) -> str | None:
        paths = []
        for source in self._eligible_sources(resource, filters):
            if (
                source.location is None
                or (
                    path_prefix is not None
                    and not source.location.startswith(path_prefix)
                )
            ):
                continue
            path = self._safe_relative_path(source.location)
            if path is not None:
                paths.append(path)
        return min(paths, key=str.casefold) if paths else None

    @staticmethod
    def _safe_relative_path(value: str | None) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.strip().replace("\\", "/")
        parsed = urlsplit(normalized)
        if parsed.scheme or parsed.netloc or "\x00" in normalized:
            return None
        parts = []
        for part in normalized.split("/"):
            if part in {"", "."}:
                continue
            if part == ".." or any(ord(char) < 32 for char in part):
                return None
            parts.append(part)
        if not parts:
            return None
        relative = "/".join(parts)
        if len(relative.encode("utf-8")) > _MAX_RELATIVE_PATH_BYTES:
            return None
        return relative

    @staticmethod
    def _mime_category(mime_type: str | None) -> str:
        if mime_type is None or not mime_type.strip():
            return "unknown"
        value = mime_type.strip().lower()
        return value.split("/", 1)[0] if "/" in value else "other"

    @staticmethod
    def _time_matches(value, lower, upper) -> bool:
        if lower is None and upper is None:
            return True
        if value is None:
            return False
        if lower is not None and value < lower:
            return False
        return upper is None or value < upper

    def _require_rich(self) -> RichRetrievalService:
        if self._rich is None:
            raise ProviderCapabilityUnavailableError(
                "unified Resource query requires Rich Retrieval composition"
            )
        return self._rich

    def _expired(self, started_at: float) -> bool:
        return self._monotonic() - started_at >= RESOURCE_QUERY_TIMEOUT_SECONDS

    @staticmethod
    def _bounded_integer(value: int, name: str, maximum: int) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 1 <= value <= maximum
        ):
            raise InvalidResourceQueryFiltersError(
                f"{name} must be between 1 and {maximum}"
            )
        return value

    @staticmethod
    def _required_text(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise InvalidResourceQueryPrimaryError(
                f"{name} must be non-empty"
            )
        return value.strip()

    @staticmethod
    def _utc(value: datetime, name: str) -> datetime:
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise InvalidResourceQueryFiltersError(
                f"{name} must be a timezone-aware datetime"
            )
        return value.astimezone(UTC)

    def _utc_or_none(self, value, name):
        return None if value is None else self._utc(value, name)

    @staticmethod
    def _bounded_text(value: str, maximum_bytes: int) -> str:
        encoded = value.encode("utf-8")
        if len(encoded) <= maximum_bytes:
            return value
        marker = "…"
        budget = maximum_bytes - len(marker.encode("utf-8"))
        prefix = encoded[:budget]
        while True:
            try:
                return prefix.decode("utf-8") + marker
            except UnicodeDecodeError:
                prefix = prefix[:-1]
