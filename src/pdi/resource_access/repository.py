from typing import Protocol

from .models import ResourceAccessSource
from .text_models import TextResourceAccessSource


class ResourceAccessRepository(Protocol):
    """Read-side mapping from canonical Asset identity to private Sources."""

    def resolve_access_sources(
        self,
        asset_id: str,
    ) -> tuple[ResourceAccessSource, ...] | None:
        """Return eligible active Sources, or None when Asset is absent."""
        ...


class ResourceTextRepository(Protocol):
    """Read-side mapping from canonical Asset identity to private text Sources."""

    def resolve_text_access_sources(
        self,
        asset_id: str,
    ) -> tuple[TextResourceAccessSource, ...] | None:
        """Return detached active file Sources, or None when Asset is absent."""
        ...
