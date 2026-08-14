from collections.abc import Mapping
from typing import Protocol

from pdi.query import ResourceSummary


class RetrievalMappingRepository(Protocol):
    """Map private Provider locators to active PDI Resources."""

    def map_active_resources(
        self,
        *,
        provider: str,
        provider_locators: tuple[str, ...],
    ) -> Mapping[str, tuple[ResourceSummary, ...]]:
        ...
