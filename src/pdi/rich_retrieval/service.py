from datetime import UTC, datetime

from pdi.observation.predicates import PREDICATES
from pdi.person_identity import normalize_person_label_query
from pdi.query import InvalidQueryError
from pdi.retrieval import (
    ProviderCapabilityUnavailableError,
    RetrievalService,
)

from .models import (
    ObservationTextPrimary,
    PersonLabelPrimary,
    ProviderSemanticPrimary,
    RetrievalStage,
    RichCandidate,
    RichFilters,
    RichPrimary,
    RichRetrievalHit,
    RichRetrievalResult,
)
from .repository import RichRetrievalRepository


PRIMARY_CANDIDATE_LIMIT = 50
MAX_PRIMARY_CANDIDATE_LIMIT = 100
DEFAULT_RICH_RESULT_LIMIT = 10
MAX_RICH_RESULT_LIMIT = 20


class RichRetrievalService:
    """Compose one bounded primary with deterministic PDI filters."""

    def __init__(
        self,
        repository: RichRetrievalRepository,
        retrieval_service: RetrievalService | None = None,
    ) -> None:
        self._repository = repository
        self._retrieval_service = retrieval_service

    def retrieve_resources(
        self,
        *,
        primary: RichPrimary,
        filters: RichFilters | None = None,
        limit: int = DEFAULT_RICH_RESULT_LIMIT,
    ) -> RichRetrievalResult:
        validated_limit = self._limit(limit)
        return self._select_resources(
            primary=primary,
            filters=filters or RichFilters(),
            candidate_limit=PRIMARY_CANDIDATE_LIMIT,
            result_limit=validated_limit,
        )

    def select_resources(
        self,
        *,
        primary: RichPrimary,
        filters: RichFilters | None = None,
        candidate_limit: int,
    ) -> RichRetrievalResult:
        """Reuse one Rich primary and its filters under an explicit bound."""

        validated_candidate_limit = self._candidate_limit(candidate_limit)
        return self._select_resources(
            primary=primary,
            filters=filters or RichFilters(),
            candidate_limit=validated_candidate_limit,
            result_limit=validated_candidate_limit,
        )

    def load_filter_signals(
        self,
        *,
        resource_refs: tuple[str, ...],
        filters: RichFilters,
    ):
        """Load current filter signals through the validated read boundary."""

        return self._repository.load_rich_filter_signals(
            resource_refs=resource_refs,
            filters=self._filters(filters),
        )

    def _select_resources(
        self,
        *,
        primary: RichPrimary,
        filters: RichFilters,
        candidate_limit: int,
        result_limit: int,
    ) -> RichRetrievalResult:
        validated_primary = self._primary(primary)
        validated_filters = self._filters(filters)

        candidates, unmapped_count, primary_stage = (
            self._execute_primary(
                validated_primary,
                candidate_limit=candidate_limit,
            )
        )
        stages = [primary_stage]
        remaining = list(candidates)

        has_metadata_filter = any((
            validated_filters.provider,
            validated_filters.resource_type,
            validated_filters.mime_type,
            validated_filters.mime_category,
            validated_filters.path_prefix,
        ))
        has_captured_filter = (
            validated_filters.captured_from is not None
            or validated_filters.captured_to is not None
        )
        has_file_modified_filter = (
            validated_filters.file_modified_from is not None
            or validated_filters.file_modified_to is not None
        )
        has_predicate_filter = bool(
            validated_filters.required_predicates
        )
        include_captured_signal = (
            has_captured_filter
            or "media.captured_at"
            in validated_filters.required_predicates
        )
        include_file_modified_signal = (
            has_file_modified_filter
            or "file.modified_at"
            in validated_filters.required_predicates
        )

        signals = {}
        if remaining and (
            has_metadata_filter
            or has_captured_filter
            or has_file_modified_filter
            or has_predicate_filter
        ):
            signals = self._repository.load_rich_filter_signals(
                resource_refs=tuple(
                    candidate.resource.resource_ref
                    for candidate in remaining
                ),
                filters=validated_filters,
            )

        if has_metadata_filter:
            before = len(remaining)
            remaining = [
                candidate
                for candidate in remaining
                if (
                    candidate.resource.resource_type
                    == (validated_filters.resource_type or "file")
                    and signals[candidate.resource.resource_ref]
                    .source_metadata_match
                )
            ]
            stages.append(RetrievalStage(
                "source_metadata_filter",
                before,
                len(remaining),
            ))

        if has_captured_filter:
            before = len(remaining)
            remaining = [
                candidate
                for candidate in remaining
                if self._captured_matches(
                    signals[candidate.resource.resource_ref].captured_at,
                    validated_filters,
                )
            ]
            stages.append(RetrievalStage(
                "captured_at_filter",
                before,
                len(remaining),
            ))

        if has_file_modified_filter:
            before = len(remaining)
            remaining = [
                candidate
                for candidate in remaining
                if self._file_modified_matches(
                    signals[candidate.resource.resource_ref]
                    .file_modified_at,
                    validated_filters,
                )
            ]
            stages.append(RetrievalStage(
                "file_modified_at_filter",
                before,
                len(remaining),
            ))

        if has_predicate_filter:
            before = len(remaining)
            required = set(validated_filters.required_predicates)
            remaining = [
                candidate
                for candidate in remaining
                if required.issubset(
                    signals[candidate.resource.resource_ref]
                    .current_predicates
                )
            ]
            stages.append(RetrievalStage(
                "required_predicates_filter",
                before,
                len(remaining),
            ))

        hits = tuple(
            RichRetrievalHit(
                resource=candidate.resource,
                source_rank=candidate.source_rank,
                matched_predicates=self._matched_predicates(
                    candidate,
                    validated_filters,
                ),
                captured_at=(
                    signals[candidate.resource.resource_ref].captured_at
                    if include_captured_signal
                    else None
                ),
                file_modified_at=(
                    signals[candidate.resource.resource_ref]
                    .file_modified_at
                    if include_file_modified_signal
                    else None
                ),
            )
            for candidate in remaining[:result_limit]
        )
        stages.append(RetrievalStage(
            "final_limit",
            len(remaining),
            len(hits),
        ))
        return RichRetrievalResult(
            hits=hits,
            stages=tuple(stages),
            unmapped_hit_count=unmapped_count,
        )

    def _execute_primary(
        self,
        primary: RichPrimary,
        *,
        candidate_limit: int,
    ) -> tuple[tuple[RichCandidate, ...], int, RetrievalStage]:
        if isinstance(primary, ProviderSemanticPrimary):
            if self._retrieval_service is None:
                raise ProviderCapabilityUnavailableError(
                    "Provider retrieval service is unavailable"
                )
            result = self._retrieval_service.retrieve_resources(
                query=primary.query,
                provider=primary.provider,
                limit=candidate_limit,
            )
            candidates = tuple(
                RichCandidate(
                    resource=hit.resource,
                    source_rank=hit.rank,
                )
                for hit in result.hits
            )
            return (
                candidates,
                result.unmapped_hit_count,
                RetrievalStage(
                    "provider_semantic_primary",
                    0,
                    len(candidates),
                ),
            )

        if isinstance(primary, PersonLabelPrimary):
            candidates = self._repository.search_current_person_label(
                primary=primary,
                limit=candidate_limit,
            )
            return (
                candidates,
                0,
                RetrievalStage(
                    "person_label_primary",
                    0,
                    len(candidates),
                ),
            )

        candidates = self._repository.search_current_observation_text(
            primary=primary,
            limit=candidate_limit,
        )
        return (
            candidates,
            0,
            RetrievalStage(
                "observation_text_primary",
                0,
                len(candidates),
            ),
        )

    @classmethod
    def _primary(cls, primary: RichPrimary) -> RichPrimary:
        if isinstance(primary, ProviderSemanticPrimary):
            if primary.kind != "provider_semantic":
                raise InvalidQueryError(
                    "provider primary kind must be provider_semantic"
                )
            if primary.provider != "immich":
                raise InvalidQueryError(
                    "provider must be immich for Rich Retrieval V0.1"
                )
        elif isinstance(primary, ObservationTextPrimary):
            if primary.kind != "observation_text":
                raise InvalidQueryError(
                    "observation primary kind must be observation_text"
                )
            if primary.predicate not in {
                "media.ocr_text",
                "document.text_excerpt",
            }:
                raise InvalidQueryError(
                    "observation text predicate is unsupported"
                )
        elif isinstance(primary, PersonLabelPrimary):
            if primary.kind != "person_label":
                raise InvalidQueryError(
                    "person label primary kind must be person_label"
                )
        else:
            raise InvalidQueryError(
                "exactly one supported Rich Retrieval primary is required"
            )

        if isinstance(primary, PersonLabelPrimary):
            try:
                normalized_label = normalize_person_label_query(
                    primary.label
                )
            except ValueError as error:
                raise InvalidQueryError(str(error)) from error
            normalized_provider = cls._optional_text(
                primary.provider,
                "provider",
            )
            if (
                normalized_label == primary.label
                and normalized_provider == primary.provider
            ):
                return primary
            return PersonLabelPrimary(
                kind=primary.kind,
                label=normalized_label,
                provider=normalized_provider,
            )

        normalized_query = cls._required_text(primary.query, "query")
        if normalized_query == primary.query:
            return primary
        if isinstance(primary, ProviderSemanticPrimary):
            return ProviderSemanticPrimary(
                kind=primary.kind,
                query=normalized_query,
                provider=primary.provider,
            )
        return ObservationTextPrimary(
            kind=primary.kind,
            query=normalized_query,
            predicate=primary.predicate,
        )

    @classmethod
    def _filters(cls, filters: RichFilters) -> RichFilters:
        mime_type = cls._optional_text(filters.mime_type, "mime_type")
        mime_category = cls._optional_text(
            filters.mime_category,
            "mime_category",
        )
        if mime_type is not None and mime_category is not None:
            raise InvalidQueryError(
                "mime_type and mime_category cannot be combined"
            )
        if mime_category is not None:
            if "/" in mime_category:
                raise InvalidQueryError(
                    "mime_category must not contain /"
                )
            mime_category = mime_category.lower()

        resource_type = cls._optional_text(
            filters.resource_type,
            "resource_type",
        )
        if resource_type is not None and resource_type != "file":
            raise InvalidQueryError("resource_type must be file")

        captured_from = cls._utc_datetime(
            filters.captured_from,
            "captured_from",
        )
        captured_to = cls._utc_datetime(
            filters.captured_to,
            "captured_to",
        )
        if (
            captured_from is not None
            and captured_to is not None
            and captured_from >= captured_to
        ):
            raise InvalidQueryError(
                "captured_from must be earlier than captured_to"
            )

        file_modified_from = cls._utc_datetime(
            filters.file_modified_from,
            "file_modified_from",
        )
        file_modified_to = cls._utc_datetime(
            filters.file_modified_to,
            "file_modified_to",
        )
        if (
            file_modified_from is not None
            and file_modified_to is not None
            and file_modified_from >= file_modified_to
        ):
            raise InvalidQueryError(
                "file_modified_from must be earlier than "
                "file_modified_to"
            )

        required: list[str] = []
        for predicate in filters.required_predicates:
            name = cls._required_text(predicate, "required_predicate")
            if name not in PREDICATES:
                raise InvalidQueryError(
                    f"unknown required predicate: {name}"
                )
            if name not in required:
                required.append(name)

        return RichFilters(
            provider=cls._optional_text(filters.provider, "provider"),
            resource_type=resource_type,
            mime_type=mime_type,
            mime_category=mime_category,
            path_prefix=cls._optional_text(
                filters.path_prefix,
                "path_prefix",
            ),
            captured_from=captured_from,
            captured_to=captured_to,
            file_modified_from=file_modified_from,
            file_modified_to=file_modified_to,
            required_predicates=tuple(required),
        )

    @staticmethod
    def _captured_matches(
        captured_at: datetime | None,
        filters: RichFilters,
    ) -> bool:
        if captured_at is None:
            return False
        if (
            filters.captured_from is not None
            and captured_at < filters.captured_from
        ):
            return False
        return not (
            filters.captured_to is not None
            and captured_at >= filters.captured_to
        )

    @staticmethod
    def _file_modified_matches(
        file_modified_at: datetime | None,
        filters: RichFilters,
    ) -> bool:
        if file_modified_at is None:
            return False
        if (
            filters.file_modified_from is not None
            and file_modified_at < filters.file_modified_from
        ):
            return False
        return not (
            filters.file_modified_to is not None
            and file_modified_at >= filters.file_modified_to
        )

    @staticmethod
    def _matched_predicates(
        candidate: RichCandidate,
        filters: RichFilters,
    ) -> tuple[str, ...]:
        predicates = list(candidate.matched_predicates)
        if (
            filters.captured_from is not None
            or filters.captured_to is not None
        ):
            predicates.append("media.captured_at")
        if (
            filters.file_modified_from is not None
            or filters.file_modified_to is not None
        ):
            predicates.append("file.modified_at")
        predicates.extend(filters.required_predicates)
        return tuple(dict.fromkeys(predicates))

    @staticmethod
    def _limit(limit: int) -> int:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= MAX_RICH_RESULT_LIMIT
        ):
            raise InvalidQueryError("limit must be between 1 and 20")
        return limit

    @staticmethod
    def _candidate_limit(limit: int) -> int:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 2000
        ):
            raise InvalidQueryError(
                "candidate_limit must be between 1 and 2000"
            )
        return limit

    @staticmethod
    def _required_text(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise InvalidQueryError(f"{name} must be non-empty")
        return value.strip()

    @classmethod
    def _optional_text(
        cls,
        value: str | None,
        name: str,
    ) -> str | None:
        if value is None:
            return None
        return cls._required_text(value, name)

    @staticmethod
    def _utc_datetime(
        value: datetime | None,
        name: str,
    ) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise InvalidQueryError(f"{name} must be a datetime")
        try:
            offset = value.utcoffset()
        except (ValueError, OverflowError) as error:
            raise InvalidQueryError(
                f"{name} must be timezone-aware"
            ) from error
        if offset is None:
            raise InvalidQueryError(
                f"{name} must be timezone-aware"
            )
        return value.astimezone(UTC)
