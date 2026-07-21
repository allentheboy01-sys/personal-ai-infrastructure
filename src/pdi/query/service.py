from .models import AssetDetail, AssetSummary
from .repository import QueryRepository


class QueryService:
    def __init__(
        self,
        repository: QueryRepository,
    ) -> None:
        self._repository = repository

    def list_assets(self) -> tuple[AssetSummary, ...]:
        return self._repository.list_asset_summaries()

    def get_asset(
        self,
        asset_id: str,
    ) -> AssetDetail | None:
        return self._repository.get_asset_detail(asset_id)
