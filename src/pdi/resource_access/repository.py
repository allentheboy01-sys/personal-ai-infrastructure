from typing import Protocol

from .models import ResourceAccessSource


class ResourceAccessRepository(Protocol):
    """Read-side mapping from canonical Asset identity to private Sources."""

    def resolve_access_sources(
        self,
        asset_id: str,
    ) -> tuple[ResourceAccessSource, ...] | None:
        """Return eligible active Sources, or None when Asset is absent."""
        ...
