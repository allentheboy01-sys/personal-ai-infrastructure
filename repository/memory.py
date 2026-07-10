from decision import ActionType, Decision
from models import Asset, AssetSource, Blob

from .base import Repository


class InMemoryRepository(Repository):
    def __init__(self) -> None:
        self.assets: dict[str, Asset] = {}
        self.blobs: dict[str, Blob] = {}
        self.sources: dict[str, AssetSource] = {}

    def find_source(
        self,
        provider: str,
        external_id: str,
    ) -> AssetSource | None:
        for source in self.sources.values():
            if (
                source.provider == provider
                and source.external_id == external_id
            ):
                return source

        return None

    def find_blob_by_hash(self, content_hash: str) -> Blob | None:
        for blob in self.blobs.values():
            if blob.hash == content_hash:
                return blob

        return None
    
    def find_blob_by_hash_in_asset(
        self,
        content_hash: str,
        asset_id: str,
    ) -> Blob | None:
        for blob in self.blobs.values():
            if (
                blob.hash == content_hash
                and blob.asset_id == asset_id
            ):
                return blob

        return None

    def get_blob(self, blob_id: str) -> Blob | None:
        return self.blobs.get(blob_id)

    def get_asset(self, asset_id: str) -> Asset | None:
        return self.assets.get(asset_id)

    def execute(self, decision: Decision) -> None:
        for action in decision.actions:
            if action.type == ActionType.CREATE_ASSET:
                if action.asset is None:
                    raise ValueError("CREATE_ASSET requires asset")

                self.assets[action.asset.id] = action.asset

            elif action.type == ActionType.CREATE_BLOB:
                if action.blob is None:
                    raise ValueError("CREATE_BLOB requires blob")

                self.blobs[action.blob.id] = action.blob

            elif action.type == ActionType.CREATE_SOURCE:
                if action.source is None:
                    raise ValueError("CREATE_SOURCE requires source")

                self.sources[action.source.id] = action.source

            elif action.type == ActionType.UPDATE_SOURCE:
                if action.source is None:
                    raise ValueError("UPDATE_SOURCE requires source")

                if action.source.id not in self.sources:
                    raise ValueError(
                        f"Source not found: {action.source.id}"
                    )

                self.sources[action.source.id] = action.source

            else:
                raise ValueError(f"Unsupported action type: {action.type}")