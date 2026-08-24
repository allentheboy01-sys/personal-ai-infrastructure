from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from pdi.models import ResourceType

from .cursor import decode_cursor, encode_cursor, query_fingerprint
from .errors import InvalidQueryError, ResourceNotFoundError
from .models import AssetDetail, AssetSummary
from .repository import QueryRepository
from .resources import (
    ResourceAggregationQuery,
    ResourceAggregationResult,
    ResourceDetail,
    ResourceFilters,
    ResourceGroupBy,
    ResourceListPageQuery,
    ResourcePage,
    ResourceSearchPageQuery,
    ResourceSummary,
    ResourceTimeRange,
    parse_resource_ref,
)


DEFAULT_QUERY_LIMIT = 50
MAX_QUERY_LIMIT = 100
DEFAULT_RECENT_DAYS = 30
MAX_AGGREGATION_BUCKETS = 100
MAX_DAY_RANGE = timedelta(days=366)

_RECENT_OPERATION = "recent"
_SEARCH_OPERATION = "search"


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
        days: int = DEFAULT_RECENT_DAYS,
        provider: str | None = None,
        resource_type: str | None = None,
        mime_type: str | None = None,
        path_prefix: str | None = None,
        limit: int = DEFAULT_QUERY_LIMIT,
    ) -> tuple[ResourceSummary, ...]:
        return self.list_resource_page(
            days=days,
            provider=provider,
            resource_type=resource_type,
            mime_type=mime_type,
            path_prefix=path_prefix,
            limit=limit,
        ).resources

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
        return self.search_resource_page(
            query=query,
            provider=provider,
            resource_type=resource_type,
            mime_type=mime_type,
            path_prefix=path_prefix,
            limit=limit,
        ).resources

    def aggregate_resources(
        self,
        *,
        group_by: ResourceGroupBy | str | None = None,
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
        provider: str | None = None,
        resource_type: str | None = None,
        mime_type: str | None = None,
        mime_category: str | None = None,
        path_prefix: str | None = None,
    ) -> ResourceAggregationResult:
        time_range = self._time_range(
            observed_from=observed_from,
            observed_to=observed_to,
        )
        filters = self._filters(
            provider=provider,
            resource_type=resource_type,
            mime_type=mime_type,
            mime_category=mime_category,
            path_prefix=path_prefix,
        )
        validated_group_by = self._group_by(group_by)

        if validated_group_by is ResourceGroupBy.PERSON_LABEL:
            if (
                time_range.observed_from is not None
                or time_range.observed_to is not None
                or filters.resource_type is not None
                or filters.mime_type is not None
                or filters.mime_category is not None
                or filters.path_prefix is not None
            ):
                raise InvalidQueryError(
                    "person_label aggregation supports only the optional "
                    "provider filter"
                )

        if validated_group_by is ResourceGroupBy.DAY:
            if (
                time_range.observed_from is None
                or time_range.observed_to is None
            ):
                raise InvalidQueryError(
                    "day aggregation requires observed_from and "
                    "observed_to"
                )
            if (
                time_range.observed_to
                - time_range.observed_from
                > MAX_DAY_RANGE
            ):
                raise InvalidQueryError(
                    "day aggregation range must not exceed 366 days"
                )

        return self._repository.aggregate_resources(
            ResourceAggregationQuery(
                time_range=time_range,
                filters=filters,
                group_by=validated_group_by,
                bucket_limit=MAX_AGGREGATION_BUCKETS,
            )
        )

    def list_resource_page(
        self,
        *,
        days: int | None = None,
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
        provider: str | None = None,
        resource_type: str | None = None,
        mime_type: str | None = None,
        mime_category: str | None = None,
        path_prefix: str | None = None,
        limit: int = DEFAULT_QUERY_LIMIT,
        cursor: str | None = None,
    ) -> ResourcePage:
        validated_limit = self._limit(limit)
        explicit_range = (
            observed_from is not None or observed_to is not None
        )
        if explicit_range and days is not None:
            raise InvalidQueryError(
                "days cannot be combined with an explicit observed range"
            )

        time_range = self._time_range(
            observed_from=observed_from,
            observed_to=observed_to,
        )
        validated_days: int | None = None
        if not explicit_range:
            validated_days = self._positive_integer(
                DEFAULT_RECENT_DAYS if days is None else days,
                "days",
            )

        filters = self._filters(
            provider=provider,
            resource_type=resource_type,
            mime_type=mime_type,
            mime_category=mime_category,
            path_prefix=path_prefix,
        )
        fingerprint = query_fingerprint(
            self._query_identity(
                operation=_RECENT_OPERATION,
                days=validated_days,
                time_range=time_range,
                filters=filters,
            )
        )

        after_observed_at: datetime | None = None
        after_asset_id: str | None = None
        if cursor is None:
            now = self._now()
            if validated_days is not None:
                try:
                    time_range = ResourceTimeRange(
                        observed_from=(
                            now - timedelta(days=validated_days)
                        ),
                        observed_to=None,
                    )
                except OverflowError as error:
                    raise InvalidQueryError(
                        "days is outside the supported range"
                    ) from error
            snapshot_to = self._snapshot_to(
                time_range.observed_to,
                now,
            )
        else:
            payload = self._validated_cursor(
                cursor,
                operation=_RECENT_OPERATION,
                fingerprint=fingerprint,
            )
            time_range = self._cursor_time_range(payload)
            snapshot_to = self._cursor_datetime(
                payload,
                "snapshot_to",
            )
            position = self._cursor_mapping(payload, "position")
            after_observed_at = self._cursor_datetime(
                position,
                "observed_at",
            )
            after_asset_id = parse_resource_ref(
                self._cursor_text(position, "resource_ref")
            )

        rows = self._repository.list_resource_page(
            ResourceListPageQuery(
                time_range=time_range,
                filters=filters,
                snapshot_to=snapshot_to,
                after_observed_at=after_observed_at,
                after_asset_id=after_asset_id,
                limit=validated_limit + 1,
            )
        )
        resources = rows[:validated_limit]
        next_cursor = None
        if len(rows) > validated_limit:
            last_resource = resources[-1]
            next_cursor = encode_cursor(
                {
                    "operation": _RECENT_OPERATION,
                    "fingerprint": fingerprint,
                    **self._cursor_range_payload(time_range),
                    "snapshot_to": snapshot_to.isoformat(),
                    "position": {
                        "observed_at": (
                            last_resource.pdi_first_observed_at.isoformat()
                        ),
                        "resource_ref": last_resource.resource_ref,
                    },
                }
            )

        return ResourcePage(
            resources=resources,
            next_cursor=next_cursor,
        )

    def search_resource_page(
        self,
        *,
        query: str,
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
        provider: str | None = None,
        resource_type: str | None = None,
        mime_type: str | None = None,
        mime_category: str | None = None,
        path_prefix: str | None = None,
        limit: int = DEFAULT_QUERY_LIMIT,
        cursor: str | None = None,
    ) -> ResourcePage:
        search_text = self._required_text(query, "query")
        validated_limit = self._limit(limit)
        time_range = self._time_range(
            observed_from=observed_from,
            observed_to=observed_to,
        )
        filters = self._filters(
            provider=provider,
            resource_type=resource_type,
            mime_type=mime_type,
            mime_category=mime_category,
            path_prefix=path_prefix,
        )
        fingerprint = query_fingerprint(
            {
                **self._query_identity(
                    operation=_SEARCH_OPERATION,
                    days=None,
                    time_range=time_range,
                    filters=filters,
                ),
                "query": search_text,
            }
        )

        after_title: str | None = None
        after_asset_id: str | None = None
        if cursor is None:
            now = self._now()
            snapshot_to = self._snapshot_to(
                time_range.observed_to,
                now,
            )
        else:
            payload = self._validated_cursor(
                cursor,
                operation=_SEARCH_OPERATION,
                fingerprint=fingerprint,
            )
            time_range = self._cursor_time_range(payload)
            snapshot_to = self._cursor_datetime(
                payload,
                "snapshot_to",
            )
            position = self._cursor_mapping(payload, "position")
            after_title = self._cursor_string(position, "title")
            after_asset_id = parse_resource_ref(
                self._cursor_text(position, "resource_ref")
            )

        rows = self._repository.search_resource_page(
            ResourceSearchPageQuery(
                query=search_text,
                time_range=time_range,
                filters=filters,
                snapshot_to=snapshot_to,
                after_title=after_title,
                after_asset_id=after_asset_id,
                limit=validated_limit + 1,
            )
        )
        resources = rows[:validated_limit]
        next_cursor = None
        if len(rows) > validated_limit:
            last_resource = resources[-1]
            next_cursor = encode_cursor(
                {
                    "operation": _SEARCH_OPERATION,
                    "fingerprint": fingerprint,
                    **self._cursor_range_payload(time_range),
                    "snapshot_to": snapshot_to.isoformat(),
                    "position": {
                        "title": last_resource.display_name,
                        "resource_ref": last_resource.resource_ref,
                    },
                }
            )

        return ResourcePage(
            resources=resources,
            next_cursor=next_cursor,
        )

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

    def _now(self) -> datetime:
        return self._aware_utc(self._clock(), "clock")

    @staticmethod
    def _snapshot_to(
        observed_to: datetime | None,
        now: datetime,
    ) -> datetime:
        if observed_to is None:
            return now
        return min(observed_to, now)

    @classmethod
    def _time_range(
        cls,
        *,
        observed_from: datetime | None,
        observed_to: datetime | None,
    ) -> ResourceTimeRange:
        normalized_from = (
            None
            if observed_from is None
            else cls._aware_utc(observed_from, "observed_from")
        )
        normalized_to = (
            None
            if observed_to is None
            else cls._aware_utc(observed_to, "observed_to")
        )
        if (
            normalized_from is not None
            and normalized_to is not None
            and normalized_from >= normalized_to
        ):
            raise InvalidQueryError(
                "observed_from must be earlier than observed_to"
            )
        return ResourceTimeRange(
            observed_from=normalized_from,
            observed_to=normalized_to,
        )

    @staticmethod
    def _aware_utc(value: datetime, name: str) -> datetime:
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

    @classmethod
    def _filters(
        cls,
        *,
        provider: str | None,
        resource_type: str | None,
        mime_type: str | None,
        mime_category: str | None,
        path_prefix: str | None,
    ) -> ResourceFilters:
        validated_mime_type = cls._optional_text(
            mime_type,
            "mime_type",
        )
        validated_mime_category = cls._optional_text(
            mime_category,
            "mime_category",
        )
        if (
            validated_mime_type is not None
            and validated_mime_category is not None
        ):
            raise InvalidQueryError(
                "mime_type and mime_category cannot be combined"
            )
        if validated_mime_category is not None:
            if "/" in validated_mime_category:
                raise InvalidQueryError(
                    "mime_category must not contain /"
                )
            validated_mime_category = validated_mime_category.lower()

        return ResourceFilters(
            provider=cls._optional_text(provider, "provider"),
            resource_type=cls._resource_type(resource_type),
            mime_type=validated_mime_type,
            mime_category=validated_mime_category,
            path_prefix=cls._optional_text(
                path_prefix,
                "path_prefix",
            ),
        )

    @staticmethod
    def _group_by(
        value: ResourceGroupBy | str | None,
    ) -> ResourceGroupBy | None:
        if value is None:
            return None
        try:
            return ResourceGroupBy(value)
        except (ValueError, TypeError) as error:
            raise InvalidQueryError(
                "group_by must be provider, day, mime_type, or "
                "mime_category, or person_label"
            ) from error

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
        if resource_type is not None and resource_type not in {
            item.value for item in ResourceType
        }:
            raise InvalidQueryError(
                "resource_type must be file or message"
            )
        return resource_type

    @staticmethod
    def _query_identity(
        *,
        operation: str,
        days: int | None,
        time_range: ResourceTimeRange,
        filters: ResourceFilters,
    ) -> dict[str, object]:
        return {
            "operation": operation,
            "days": days,
            "observed_from": QueryService._iso_or_none(
                time_range.observed_from
            ),
            "observed_to": QueryService._iso_or_none(
                time_range.observed_to
            ),
            "provider": filters.provider,
            "resource_type": filters.resource_type,
            "mime_type": filters.mime_type,
            "mime_category": filters.mime_category,
            "path_prefix": filters.path_prefix,
        }

    @staticmethod
    def _iso_or_none(value: datetime | None) -> str | None:
        return None if value is None else value.isoformat()

    @staticmethod
    def _cursor_range_payload(
        time_range: ResourceTimeRange,
    ) -> dict[str, object]:
        return {
            "observed_from": QueryService._iso_or_none(
                time_range.observed_from
            ),
            "observed_to": QueryService._iso_or_none(
                time_range.observed_to
            ),
        }

    @staticmethod
    def _validated_cursor(
        cursor: str,
        *,
        operation: str,
        fingerprint: str,
    ) -> dict[str, Any]:
        payload = decode_cursor(cursor)
        if payload.get("operation") != operation:
            raise InvalidQueryError(
                "cursor does not belong to this operation"
            )
        if payload.get("fingerprint") != fingerprint:
            raise InvalidQueryError(
                "cursor does not match the query"
            )
        return payload

    @classmethod
    def _cursor_time_range(
        cls,
        payload: Mapping[str, Any],
    ) -> ResourceTimeRange:
        observed_from = cls._optional_cursor_datetime(
            payload,
            "observed_from",
        )
        observed_to = cls._optional_cursor_datetime(
            payload,
            "observed_to",
        )
        return cls._time_range(
            observed_from=observed_from,
            observed_to=observed_to,
        )

    @classmethod
    def _optional_cursor_datetime(
        cls,
        payload: Mapping[str, Any],
        name: str,
    ) -> datetime | None:
        value = payload.get(name)
        if value is None:
            return None
        if not isinstance(value, str):
            raise InvalidQueryError("cursor is malformed")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise InvalidQueryError("cursor is malformed") from error
        return cls._aware_utc(parsed, name)

    @classmethod
    def _cursor_datetime(
        cls,
        payload: Mapping[str, Any],
        name: str,
    ) -> datetime:
        value = cls._optional_cursor_datetime(payload, name)
        if value is None:
            raise InvalidQueryError("cursor is malformed")
        return value

    @staticmethod
    def _cursor_mapping(
        payload: Mapping[str, Any],
        name: str,
    ) -> Mapping[str, Any]:
        value = payload.get(name)
        if not isinstance(value, dict):
            raise InvalidQueryError("cursor is malformed")
        return value

    @staticmethod
    def _cursor_text(
        payload: Mapping[str, Any],
        name: str,
    ) -> str:
        value = payload.get(name)
        if not isinstance(value, str) or not value:
            raise InvalidQueryError("cursor is malformed")
        return value

    @staticmethod
    def _cursor_string(
        payload: Mapping[str, Any],
        name: str,
    ) -> str:
        value = payload.get(name)
        if not isinstance(value, str):
            raise InvalidQueryError("cursor is malformed")
        return value
