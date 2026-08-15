from collections.abc import Mapping
from typing import Protocol

from .models import (
    ObservationTextPrimary,
    RichCandidate,
    RichFilterSignals,
    RichFilters,
)


class RichRetrievalRepository(Protocol):
    """Bounded read operations required by Rich Retrieval V0.1."""

    def search_current_observation_text(
        self,
        *,
        primary: ObservationTextPrimary,
        limit: int,
    ) -> tuple[RichCandidate, ...]:
        """Return deterministic current-Statement candidates."""
        ...

    def load_rich_filter_signals(
        self,
        *,
        resource_refs: tuple[str, ...],
        filters: RichFilters,
    ) -> Mapping[str, RichFilterSignals]:
        """Batch-load source eligibility and current predicate signals."""
        ...
