from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from .errors import InvalidResourceRefError


RESOURCE_REF_PREFIX = "pdi:resource:"
RESOURCE_TIME_BASIS = "pdi_first_observed_at"
PERSON_LABEL_TIME_BASIS = "current_person_source"


class ResourceGroupBy(StrEnum):
    PROVIDER = "provider"
    DAY = "day"
    MIME_TYPE = "mime_type"
    MIME_CATEGORY = "mime_category"
    PERSON_LABEL = "person_label"


@dataclass(frozen=True, slots=True)
class ResourceTimeRange:
    observed_from: datetime | None
    observed_to: datetime | None


@dataclass(frozen=True, slots=True)
class ResourceFilters:
    provider: str | None
    resource_type: str | None
    mime_type: str | None
    mime_category: str | None
    path_prefix: str | None


@dataclass(frozen=True, slots=True)
class ResourceAggregationBucket:
    key: str
    count: int


@dataclass(frozen=True, slots=True)
class ResourceAggregationResult:
    time_basis: str
    time_range: ResourceTimeRange
    applied_filters: ResourceFilters
    group_by: ResourceGroupBy | None
    total_count: int
    buckets: tuple[ResourceAggregationBucket, ...]
    buckets_truncated: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "buckets", tuple(self.buckets))


@dataclass(frozen=True, slots=True)
class ResourceSourceSummary:
    provider: str
    location: str | None
    name: str | None
    mime_type: str | None
    size_bytes: int | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class ResourceSummary:
    resource_ref: str
    resource_type: str
    display_name: str
    pdi_first_observed_at: datetime
    sources: tuple[ResourceSourceSummary, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "sources", tuple(self.sources))


@dataclass(frozen=True, slots=True)
class ContentSummary:
    mime_type: str | None
    size_bytes: int | None
    checksum: str | None


@dataclass(frozen=True, slots=True)
class ResourceDetail:
    resource_ref: str
    resource_type: str
    display_name: str
    pdi_first_observed_at: datetime
    sources: tuple[ResourceSourceSummary, ...]
    content_variants: tuple[ContentSummary, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(
            self,
            "content_variants",
            tuple(self.content_variants),
        )


@dataclass(frozen=True, slots=True)
class ResourcePage:
    resources: tuple[ResourceSummary, ...]
    next_cursor: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "resources", tuple(self.resources))


@dataclass(frozen=True, slots=True)
class RecentResourcesQuery:
    created_since: datetime
    provider: str | None
    resource_type: str | None
    mime_type: str | None
    path_prefix: str | None
    limit: int


@dataclass(frozen=True, slots=True)
class ResourceSearchQuery:
    query: str
    provider: str | None
    resource_type: str | None
    mime_type: str | None
    path_prefix: str | None
    limit: int


@dataclass(frozen=True, slots=True)
class ResourceAggregationQuery:
    time_range: ResourceTimeRange
    filters: ResourceFilters
    group_by: ResourceGroupBy | None
    bucket_limit: int


@dataclass(frozen=True, slots=True)
class ResourceListPageQuery:
    time_range: ResourceTimeRange
    filters: ResourceFilters
    snapshot_to: datetime
    after_observed_at: datetime | None
    after_asset_id: str | None
    limit: int


@dataclass(frozen=True, slots=True)
class ResourceSearchPageQuery:
    query: str
    time_range: ResourceTimeRange
    filters: ResourceFilters
    snapshot_to: datetime
    after_title: str | None
    after_asset_id: str | None
    limit: int


def format_resource_ref(asset_id: str | UUID) -> str:
    try:
        parsed_id = UUID(str(asset_id))
    except (ValueError, TypeError, AttributeError) as error:
        raise InvalidResourceRefError(
            "Resource identity must be a valid UUID"
        ) from error

    return f"{RESOURCE_REF_PREFIX}{parsed_id}"


def parse_resource_ref(resource_ref: str) -> str:
    if not isinstance(resource_ref, str) or not resource_ref.startswith(
        RESOURCE_REF_PREFIX
    ):
        raise InvalidResourceRefError(
            "Resource reference must start with pdi:resource:"
        )

    raw_id = resource_ref[len(RESOURCE_REF_PREFIX) :]

    try:
        parsed_id = UUID(raw_id)
    except (ValueError, TypeError, AttributeError) as error:
        raise InvalidResourceRefError(
            "Resource reference must contain a valid UUID"
        ) from error

    if str(parsed_id) != raw_id:
        raise InvalidResourceRefError(
            "Resource reference UUID must use canonical form"
        )

    return str(parsed_id)
