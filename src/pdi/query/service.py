from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from .errors import InvalidQueryError, ResourceNotFoundError
from .models import AssetDetail, AssetSummary
from .repository import QueryRepository
from .resources import (
    RecentResourcesQuery,
    ResourceDetail,
    ResourceSearchQuery,
    ResourceSummary,
    parse_resource_ref,
)


DEFAULT_QUERY_LIMIT = 50
MAX_QUERY_LIMIT = 100


class QueryService:
    def __init__(
        self,
        repository: QueryRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def list_assets(self) -> tuple[AssetSummary, ...]:
        return self._repository.list_asset_summaries()

    def get_asset(
        self,
        asset_id: str,
    ) -> AssetDetail | None:
        return self._repository.get_asset_detail(asset_id)

    def list_recent_resources(
        self,
        *,
        days: int = 30,
        provider: str | None = None,
        resource_type: str | None = None,
        mime_type: str | None = None,
        path_prefix: str | None = None,
        limit: int = DEFAULT_QUERY_LIMIT,
    ) -> tuple[ResourceSummary, ...]:
        validated_days = self._positive_integer(days, "days")
        validated_limit = self._limit(limit)
        try:
            created_since = self._clock() - timedelta(
                days=validated_days
            )
        except OverflowError as error:
            raise InvalidQueryError(
                "days is outside the supported range"
            ) from error

        query = RecentResourcesQuery(
            created_since=created_since,
            provider=self._optional_text(provider, "provider"),
            resource_type=self._resource_type(resource_type),
            mime_type=self._optional_text(mime_type, "mime_type"),
            path_prefix=self._optional_text(
                path_prefix,
                "path_prefix",
            ),
            limit=validated_limit,
        )
        return self._repository.list_recent_resources(query)

    def search_resources(
        self,
        *,
        query: str,
        provider: str | None = None,
        resource_type: str | None = None,
        mime_type: str | None = None,
        path_prefix: str | None = None,
        limit: int = DEFAULT_QUERY_LIMIT,
    ) -> tuple[ResourceSummary, ...]:
        search_text = self._required_text(query, "query")
        search_query = ResourceSearchQuery(
            query=search_text,
            provider=self._optional_text(provider, "provider"),
            resource_type=self._resource_type(resource_type),
            mime_type=self._optional_text(mime_type, "mime_type"),
            path_prefix=self._optional_text(
                path_prefix,
                "path_prefix",
            ),
            limit=self._limit(limit),
        )
        return self._repository.search_resources(search_query)

    def get_resource(
        self,
        resource_ref: str,
    ) -> ResourceDetail:
        asset_id = parse_resource_ref(resource_ref)
        detail = self._repository.get_resource_detail(asset_id)

        if detail is None:
            raise ResourceNotFoundError(
                f"Resource not found: {resource_ref}"
            )

        return detail

    @staticmethod
    def _positive_integer(value: int, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise InvalidQueryError(
                f"{name} must be a positive integer"
            )
        return value

    @classmethod
    def _limit(cls, value: int) -> int:
        limit = cls._positive_integer(value, "limit")
        if limit > MAX_QUERY_LIMIT:
            raise InvalidQueryError(
                f"limit must not exceed {MAX_QUERY_LIMIT}"
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

    @classmethod
    def _resource_type(cls, value: str | None) -> str | None:
        resource_type = cls._optional_text(value, "resource_type")
        if resource_type is not None and resource_type != "file":
            raise InvalidQueryError(
                "resource_type must be file"
            )
        return resource_type
