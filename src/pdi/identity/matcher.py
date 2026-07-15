from dataclasses import replace
from pathlib import Path

from adapters.base import ProviderFact
from decision import (
    Action,
    ActionType,
    Decision,
    RequirementType,
)
from models import Asset, AssetSource, Blob
from repository import Repository


class Matcher:
    def match(
        self,
        fact: ProviderFact,
        repository: Repository,
    ) -> Decision:
        invalid_reason = self._validate_fact(fact)

        if invalid_reason is not None:
            return Decision(
                actions=[],
                reason=invalid_reason,
                confidence=0.0,
            )

        if fact.kind == "folder":
            return Decision(
                actions=[],
                reason="folder_ignored_in_v0_1",
                confidence=1.0,
            )

        existing_source = repository.find_source(
            provider=fact.provider,
            external_id=fact.external_id,
        )

        if existing_source is None:
            return self._match_new_source(
                fact=fact,
                repository=repository,
            )

        return self._match_existing_source(
            fact=fact,
            source=existing_source,
            repository=repository,
        )

    def _match_new_source(
        self,
        fact: ProviderFact,
        repository: Repository,
    ) -> Decision:
        content_hash = self._get_string_attribute(
            fact,
            "content_hash",
        )

        if content_hash is None:
            return Decision(
                actions=[],
                requirements=[
                    RequirementType.CONTENT_HASH,
                ],
                reason="content_hash_required",
                confidence=0.0,
            )

        # 新 Source 可以在整个 World Model 中查找相同内容。
        existing_blob = repository.find_blob_by_hash(
            content_hash,
        )

        if existing_blob is not None:
            source = self._build_source(
                fact=fact,
                blob_id=existing_blob.id,
            )

            return Decision(
                actions=[
                    Action(
                        type=ActionType.CREATE_SOURCE,
                        source=source,
                    ),
                ],
                reason="new_source_existing_blob",
                confidence=1.0,
            )

        asset = Asset(
            title=self._build_asset_title(fact),
        )

        blob = self._build_blob(
            fact=fact,
            asset_id=asset.id,
            content_hash=content_hash,
        )

        source = self._build_source(
            fact=fact,
            blob_id=blob.id,
        )

        return Decision(
            actions=[
                Action(
                    type=ActionType.CREATE_ASSET,
                    asset=asset,
                ),
                Action(
                    type=ActionType.CREATE_BLOB,
                    blob=blob,
                ),
                Action(
                    type=ActionType.CREATE_SOURCE,
                    source=source,
                ),
            ],
            reason="new_source_new_blob",
            confidence=1.0,
        )

    def _match_existing_source(
        self,
        fact: ProviderFact,
        source: AssetSource,
        repository: Repository,
    ) -> Decision:
        incoming_version_tag = self._get_string_attribute(
            fact,
            "version_tag",
        )

        # Provider 版本没有变化。
        if source.version_tag == incoming_version_tag:
            if self._source_state_is_unchanged(
                fact=fact,
                source=source,
            ):
                return Decision(
                    actions=[],
                    reason="source_unchanged",
                    confidence=1.0,
                )

            updated_source = self._updated_source(
                source=source,
                fact=fact,
                blob_id=source.blob_id,
            )

            return Decision(
                actions=[
                    Action(
                        type=ActionType.UPDATE_SOURCE,
                        source=updated_source,
                    ),
                ],
                reason="source_metadata_changed",
                confidence=1.0,
            )

        # Provider 版本变化，需要真实内容 Hash。
        content_hash = self._get_string_attribute(
            fact,
            "content_hash",
        )
        if content_hash is None:
            return Decision(
                actions=[],
                requirements=[
                    RequirementType.CONTENT_HASH,
                ],
                reason="content_hash_required",
                confidence=0.0,
            )

        if source.blob_id is None:
            return Decision(
                actions=[],
                reason="existing_source_has_no_blob",
                confidence=0.0,
            )

        current_blob = repository.get_blob(
            source.blob_id,
        )

        if current_blob is None:
            return Decision(
                actions=[],
                reason="existing_source_blob_not_found",
                confidence=0.0,
            )

        if current_blob.asset_id is None:
            return Decision(
                actions=[],
                reason="existing_blob_has_no_asset",
                confidence=0.0,
            )

        # 已有 Source 必须维持原 Asset 生命周期。
        # 因此只能在当前 Asset 内复用相同 Hash 的 Blob。
        existing_blob_in_asset = (
            repository.find_blob_by_hash_in_asset(
                content_hash=content_hash,
                asset_id=current_blob.asset_id,
            )
        )

        if existing_blob_in_asset is not None:
            updated_source = self._updated_source(
                source=source,
                fact=fact,
                blob_id=existing_blob_in_asset.id,
            )

            return Decision(
                actions=[
                    Action(
                        type=ActionType.UPDATE_SOURCE,
                        source=updated_source,
                    ),
                ],
                reason="source_returned_to_existing_blob_in_asset",
                confidence=1.0,
            )

        new_blob = self._build_blob(
            fact=fact,
            asset_id=current_blob.asset_id,
            content_hash=content_hash,
        )

        updated_source = self._updated_source(
            source=source,
            fact=fact,
            blob_id=new_blob.id,
        )

        return Decision(
            actions=[
                Action(
                    type=ActionType.CREATE_BLOB,
                    blob=new_blob,
                ),
                Action(
                    type=ActionType.UPDATE_SOURCE,
                    source=updated_source,
                ),
            ],
            reason="new_blob_for_existing_asset",
            confidence=1.0,
        )

    @staticmethod
    def _validate_fact(
        fact: ProviderFact,
    ) -> str | None:
        if not fact.provider.strip():
            return "invalid_fact_missing_provider"

        if not fact.external_id:
            return "invalid_fact_missing_external_id"

        if fact.kind not in {"file", "folder"}:
            return "invalid_fact_kind"

        return None

    @staticmethod
    def _get_string_attribute(
        fact: ProviderFact,
        key: str,
    ) -> str | None:
        value = fact.attributes.get(key)

        if isinstance(value, str) and value:
            return value

        return None

    @staticmethod
    def _source_state_is_unchanged(
        fact: ProviderFact,
        source: AssetSource,
    ) -> bool:
        return (
            source.path == fact.attributes.get("path")
            and source.name == fact.name
            and source.version_tag
            == fact.attributes.get("version_tag")
        )

    @staticmethod
    def _build_source(
        fact: ProviderFact,
        blob_id: str,
    ) -> AssetSource:
        path = fact.attributes.get("path")
        version_tag = fact.attributes.get("version_tag")

        return AssetSource(
            blob_id=blob_id,
            provider=fact.provider,
            external_id=fact.external_id,
            path=path if isinstance(path, str) else None,
            name=fact.name,
            version_tag=(
                version_tag
                if isinstance(version_tag, str)
                else None
            ),
        )

    @staticmethod
    def _updated_source(
        source: AssetSource,
        fact: ProviderFact,
        blob_id: str | None,
    ) -> AssetSource:
        path = fact.attributes.get("path")
        version_tag = fact.attributes.get("version_tag")

        return replace(
            source,
            blob_id=blob_id,
            path=path if isinstance(path, str) else None,
            name=fact.name,
            version_tag=(
                version_tag
                if isinstance(version_tag, str)
                else None
            ),
        )

    @staticmethod
    def _build_blob(
        fact: ProviderFact,
        asset_id: str,
        content_hash: str,
    ) -> Blob:
        size = fact.attributes.get("size")

        if not isinstance(size, int):
            size = None

        mime_type = fact.attributes.get("mime_type")

        if not isinstance(mime_type, str):
            mime_type = None

        return Blob(
            asset_id=asset_id,
            hash=content_hash,
            size=size,
            mime_type=mime_type,
        )

    @staticmethod
    def _build_asset_title(
        fact: ProviderFact,
    ) -> str:
        if not fact.name:
            return "Untitled Asset"

        suffix = Path(fact.name).suffix

        if suffix:
            return fact.name.removesuffix(suffix)

        return fact.name