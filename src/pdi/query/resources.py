from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .errors import InvalidResourceRefError


RESOURCE_REF_PREFIX = "pdi:resource:"


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
