from typing import Protocol

from .models import AssetDetail, AssetSummary


class QueryRepository(Protocol):
    """Read-side persistence contract for stable Query models."""

    def list_asset_summaries(
        self,
    ) -> tuple[AssetSummary, ...]:
        """Return the available Assets without ORM or Domain objects."""
        ...

    def get_asset_detail(
        self,
        asset_id: str,
    ) -> AssetDetail | None:
        """Return one Asset with its Blobs and Sources."""
        ...
