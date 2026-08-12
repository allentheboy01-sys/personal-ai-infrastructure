from typing import Protocol

from .models import AssetDetail, AssetSummary
from .resources import (
    RecentResourcesQuery,
    ResourceAggregationQuery,
    ResourceAggregationResult,
    ResourceDetail,
    ResourceListPageQuery,
    ResourceSearchQuery,
    ResourceSearchPageQuery,
    ResourceSummary,
)


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

    def list_recent_resources(
        self,
        query: RecentResourcesQuery,
    ) -> tuple[ResourceSummary, ...]:
        """Return recent active Resource projections."""
        ...

    def search_resources(
        self,
        query: ResourceSearchQuery,
    ) -> tuple[ResourceSummary, ...]:
        """Search active Resource projections by metadata."""
        ...

    def get_resource_detail(
        self,
        asset_id: str,
    ) -> ResourceDetail | None:
        """Return one detached Resource projection."""
        ...

    def aggregate_resources(
        self,
        query: ResourceAggregationQuery,
    ) -> ResourceAggregationResult:
        """Count and optionally group active Resource projections."""
        ...

    def list_resource_page(
        self,
        query: ResourceListPageQuery,
    ) -> tuple[ResourceSummary, ...]:
        """Return one keyset page, including an optional lookahead row."""
        ...

    def search_resource_page(
        self,
        query: ResourceSearchPageQuery,
    ) -> tuple[ResourceSummary, ...]:
        """Return one lexical search keyset page."""
        ...
