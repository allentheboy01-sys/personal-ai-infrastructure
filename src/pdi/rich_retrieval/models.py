from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as validated_dataclass

from pdi.query import ResourceSummary


ProviderSemanticKind: TypeAlias = Literal["provider_semantic"]
ObservationTextKind: TypeAlias = Literal["observation_text"]
ObservationTextPredicate: TypeAlias = Literal[
    "media.ocr_text",
    "document.text_excerpt",
]


@validated_dataclass(
    frozen=True,
    slots=True,
    config=ConfigDict(extra="forbid"),
)
class ProviderSemanticPrimary:
    kind: ProviderSemanticKind
    query: str
    provider: Literal["immich"]


@validated_dataclass(
    frozen=True,
    slots=True,
    config=ConfigDict(extra="forbid"),
)
class ObservationTextPrimary:
    kind: ObservationTextKind
    query: str
    predicate: ObservationTextPredicate


RichPrimary: TypeAlias = ProviderSemanticPrimary | ObservationTextPrimary


@validated_dataclass(
    frozen=True,
    slots=True,
    config=ConfigDict(extra="forbid"),
)
class RichFilters:
    provider: str | None = None
    resource_type: str | None = None
    mime_type: str | None = None
    mime_category: str | None = None
    path_prefix: str | None = None
    captured_from: datetime | None = None
    captured_to: datetime | None = None
    file_modified_from: datetime | None = None
    file_modified_to: datetime | None = None
    required_predicates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "required_predicates",
            tuple(self.required_predicates),
        )


@dataclass(frozen=True, slots=True)
class RichCandidate:
    resource: ResourceSummary
    source_rank: int
    matched_predicates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "matched_predicates",
            tuple(self.matched_predicates),
        )


@dataclass(frozen=True, slots=True)
class RichFilterSignals:
    resource_ref: str
    source_metadata_match: bool
    captured_at: datetime | None
    file_modified_at: datetime | None
    current_predicates: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "current_predicates",
            frozenset(self.current_predicates),
        )


@dataclass(frozen=True, slots=True)
class RetrievalStage:
    stage: str
    input_count: int
    output_count: int


@dataclass(frozen=True, slots=True)
class RichRetrievalHit:
    resource: ResourceSummary
    source_rank: int
    matched_predicates: tuple[str, ...]
    captured_at: datetime | None = None
    file_modified_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "matched_predicates",
            tuple(self.matched_predicates),
        )


@dataclass(frozen=True, slots=True)
class RichRetrievalResult:
    hits: tuple[RichRetrievalHit, ...]
    stages: tuple[RetrievalStage, ...]
    unmapped_hit_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "hits", tuple(self.hits))
        object.__setattr__(self, "stages", tuple(self.stages))
