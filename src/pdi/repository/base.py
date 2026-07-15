from abc import ABC, abstractmethod

from decision import Decision
from models import Asset, AssetSource, Blob


class Repository(ABC):
    @abstractmethod
    def find_source(
        self,
        provider: str,
        external_id: str,
    ) -> AssetSource | None:
        """根据 Provider 内部身份查找已有 Source。"""
        raise NotImplementedError

    @abstractmethod
    def find_blob_by_hash(self, content_hash: str) -> Blob | None:
        """根据内容 Hash 查找已有 Blob。"""
        raise NotImplementedError

    @abstractmethod
    def find_blob_by_hash_in_asset(
        self,
        content_hash: str,
        asset_id: str,
    ) -> Blob | None:
        """在指定 Asset 内根据内容 Hash 查找 Blob。"""
        raise NotImplementedError

    @abstractmethod
    def get_blob(self, blob_id: str) -> Blob | None:
        """根据 PDI 内部 ID 查找 Blob。"""
        raise NotImplementedError

    @abstractmethod
    def get_asset(self, asset_id: str) -> Asset | None:
        """根据 PDI 内部 ID 查找 Asset。"""
        raise NotImplementedError

    @abstractmethod
    def execute(self, decision: Decision) -> None:
        """执行 Identity 生成的 Decision。"""
        raise NotImplementedError