from pdi.query import InvalidQueryError

from .errors import RetrievalMappingError
from .models import ResourceRetrievalHit, ResourceRetrievalResult
from .provider import ProviderRetrievalAdapter
from .repository import RetrievalMappingRepository


DEFAULT_RETRIEVAL_LIMIT = 20
MAX_RETRIEVAL_LIMIT = 100


class RetrievalService:
    """Coordinate one provider query with read-only PDI mapping."""

    def __init__(
        self,
        adapter: ProviderRetrievalAdapter,
        repository: RetrievalMappingRepository,
    ) -> None:
        self._adapter = adapter
        self._repository = repository

    def retrieve_resources(
        self,
        *,
        query: str,
        provider: str,
        limit: int = DEFAULT_RETRIEVAL_LIMIT,
    ) -> ResourceRetrievalResult:
        normalized_query = self._validate_query(query)
        self._validate_limit(limit)

        if provider != self._adapter.provider or provider != "immich":
            raise InvalidQueryError(
                "provider must be immich for Provider Retrieval V0.1"
            )

        provider_hits = self._adapter.search_resources(
            query=normalized_query,
            limit=limit,
        )
        provider_locators = tuple(
            hit.provider_locator for hit in provider_hits
        )
        mappings = self._repository.map_active_resources(
            provider=provider,
            provider_locators=provider_locators,
        )

        hits: list[ResourceRetrievalHit] = []
        unmapped_hit_count = 0
        for provider_hit in provider_hits:
            resources = mappings.get(provider_hit.provider_locator, ())
            if not resources:
                unmapped_hit_count += 1
                continue
            if len(resources) != 1:
                raise RetrievalMappingError(
                    "Provider retrieval hit has an ambiguous PDI mapping"
                )
            hits.append(
                ResourceRetrievalHit(
                    resource=resources[0],
                    rank=provider_hit.rank,
                    provider=provider_hit.provider,
                    retrieval_kind="semantic",
                )
            )

        return ResourceRetrievalResult(
            hits=tuple(hits),
            provider=provider,
            retrieval_kind="semantic",
            unmapped_hit_count=unmapped_hit_count,
        )

    @staticmethod
    def _validate_query(query: str) -> str:
        if not isinstance(query, str) or not query.strip():
            raise InvalidQueryError("query must be a non-empty string")
        return query.strip()

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= MAX_RETRIEVAL_LIMIT
        ):
            raise InvalidQueryError("limit must be between 1 and 100")
