from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as validated_dataclass

from pdi.rich_retrieval import ObservationTextPredicate


@validated_dataclass(
    frozen=True,
    slots=True,
    config=ConfigDict(extra="forbid"),
)
class RecentPrimary:
    kind: Literal["recent"]


@validated_dataclass(
    frozen=True,
    slots=True,
    config=ConfigDict(extra="forbid"),
)
class MetadataTextPrimary:
    kind: Literal["metadata_text"]
    query: str


@validated_dataclass(
    frozen=True,
    slots=True,
    config=ConfigDict(extra="forbid"),
)
class ProviderSemanticPrimary:
    kind: Literal["provider_semantic"]
    query: str
    provider: str


@validated_dataclass(
    frozen=True,
    slots=True,
    config=ConfigDict(extra="forbid"),
)
class ObservationTextPrimary:
    kind: Literal["observation_text"]
    query: str
    predicate: ObservationTextPredicate


@validated_dataclass(
    frozen=True,
    slots=True,
    config=ConfigDict(extra="forbid"),
)
class PersonLabelPrimary:
    kind: Literal["person_label"]
    label: str
    provider: str | None = None


@validated_dataclass(
    frozen=True,
    slots=True,
    config=ConfigDict(extra="forbid"),
)
class PathTreePrimary:
    kind: Literal["path_tree"]
    path_prefix: str


ResourceQueryPrimary: TypeAlias = (
    RecentPrimary
    | MetadataTextPrimary
    | ProviderSemanticPrimary
    | ObservationTextPrimary
    | PersonLabelPrimary
    | PathTreePrimary
)


@validated_dataclass(
    frozen=True,
    slots=True,
    config=ConfigDict(extra="forbid"),
)
class ResourceQueryFilters:
    provider: str | None = None
    resource_type: str | None = None
    mime_type: str | None = None
    mime_category: str | None = None
    observed_from: datetime | None = None
    observed_to: datetime | None = None
    captured_from: datetime | None = None
    captured_to: datetime | None = None
    file_modified_from: datetime | None = None
    file_modified_to: datetime | None = None
    path_prefix: str | None = None
    required_predicates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "required_predicates",
            tuple(self.required_predicates),
        )


@validated_dataclass(
    frozen=True,
    slots=True,
    config=ConfigDict(extra="forbid"),
)
class ResourceQuerySort:
    basis: Literal[
        "relevance",
        "pdi_observed_at",
        "file_modified_at",
        "captured_at",
        "path",
    ]
    direction: Literal["asc", "desc"] | None = None


@dataclass(frozen=True, slots=True)
class CompactResource:
    resource_ref: str
    title: str
    resource_type: str
    mime_type: str | None
    mime_category: str | None
    providers: tuple[str, ...]
    relevant_time: datetime | None
    time_basis: str | None
    rank: int
    match_basis: str
    relative_path: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "providers", tuple(self.providers))


@dataclass(frozen=True, slots=True)
class ResourceQueryResult:
    schema: str
    query_kind: str
    snapshot: datetime
    selection_status: Literal["complete", "bounded_partial"]
    bound_reason: Literal[
        "scan_limit",
        "timeout",
        "serialized_byte_limit",
    ] | None
    scanned_count: int
    resources: tuple[CompactResource, ...]
    continuation: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "resources", tuple(self.resources))
