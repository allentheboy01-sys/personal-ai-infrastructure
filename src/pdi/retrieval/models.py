from dataclasses import dataclass
from typing import Literal

from pdi.query import ResourceSummary


RetrievalKind = Literal["semantic"]


@dataclass(frozen=True, slots=True)
class ProviderRetrievalHit:
    provider: str
    provider_locator: str
    rank: int
    provider_score: float | None = None


@dataclass(frozen=True, slots=True)
class ResourceRetrievalHit:
    resource: ResourceSummary
    rank: int
    provider: str
    retrieval_kind: RetrievalKind


@dataclass(frozen=True, slots=True)
class ResourceRetrievalResult:
    hits: tuple[ResourceRetrievalHit, ...]
    provider: str
    retrieval_kind: RetrievalKind
    unmapped_hit_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "hits", tuple(self.hits))
