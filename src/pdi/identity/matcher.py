from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from pdi.adapters.base import ProviderFact
from pdi.capability.hash import ContentEvidence
from pdi.decision import (
    Action,
    ActionType,
    Decision,
    RequirementType,
)
from pdi.models import Asset, AssetSource, Blob, ResourceType
from pdi.models.asset_source import (
    POSTGRES_BIGINT_MAX,
    validate_provider_size,
)
from pdi.repository import Repository


class ContentEvidencePolicyError(RuntimeError):
    """Transient content evidence violates a frozen Matcher invariant."""


class ProviderContentSizeMismatchError(ContentEvidencePolicyError):
    """Provider size disagrees with the exact streamed byte length."""

    def __init__(
        self,
        provider: str,
        provider_size: int,
        content_byte_length: int,
    ) -> None:
        self.provider = provider
        self.provider_size = provider_size
        self.content_byte_length = content_byte_length
        super().__init__(
            "Provider content size does not match streamed evidence: "
            f"provider={provider}"
        )


class ContentEvidenceSizeOverflowError(ContentEvidencePolicyError):
    """Streamed content cannot be represented by durable Blob.size."""


class BlobContentEvidenceInvariantError(ContentEvidencePolicyError):
    """An existing same-hash Blob has incompatible byte-length evidence."""


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

        self._get_optional_provider_size_attribute(fact, "size")

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

        self._require_matching_resource_type(
            fact=fact,
            source=existing_source,
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
        content_evidence = self._get_content_evidence(fact)

        if content_evidence is None:
            return self._content_evidence_required()

        if fact.kind == ResourceType.MESSAGE:
            return self._create_new_resource(
                fact=fact,
                content_evidence=content_evidence,
                resource_type=ResourceType.MESSAGE,
                reason="new_message_source",
            )

        # 新 Source 可以在整个 World Model 中复用相同内容。
        existing_blob = repository.find_blob_by_hash(
            content_evidence.sha256,
        )

        if existing_blob is not None:
            self._require_blob_matches_content_evidence(
                existing_blob,
                content_evidence,
                allow_legacy_unknown_size=False,
            )
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

        return self._create_new_resource(
            fact=fact,
            content_evidence=content_evidence,
            resource_type=ResourceType.FILE,
            reason="new_source_new_blob",
        )

    def _create_new_resource(
        self,
        *,
        fact: ProviderFact,
        content_evidence: ContentEvidence,
        resource_type: ResourceType,
        reason: str,
    ) -> Decision:
        asset = Asset(
            resource_type=resource_type,
            title=self._build_asset_title(fact),
        )
        blob = self._build_blob(
            fact=fact,
            asset_id=asset.id,
            content_evidence=content_evidence,
        )
        source = self._build_source(fact=fact, blob_id=blob.id)
        return Decision(
            actions=[
                Action(type=ActionType.CREATE_ASSET, asset=asset),
                Action(type=ActionType.CREATE_BLOB, blob=blob),
                Action(type=ActionType.CREATE_SOURCE, source=source),
            ],
            reason=reason,
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

        if source.version_tag == incoming_version_tag:
            return self._match_same_version_source(
                fact=fact,
                source=source,
                repository=repository,
            )

        return self._match_changed_version_source(
            fact=fact,
            source=source,
            repository=repository,
        )

    def _match_same_version_source(
        self,
        fact: ProviderFact,
        source: AssetSource,
        repository: Repository,
    ) -> Decision:
        current_blob = self._require_current_blob(
            source=source,
            repository=repository,
        )
        content_evidence = self._get_content_evidence(fact)

        if content_evidence is not None:
            return self._match_verified_existing_content(
                fact=fact,
                source=source,
                repository=repository,
                current_blob=current_blob,
                content_evidence=content_evidence,
                same_version=True,
            )

        if self._same_version_requires_content_evidence(
            fact=fact,
            source=source,
            current_blob=current_blob,
        ):
            return self._content_evidence_required()

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

    def _match_changed_version_source(
        self,
        fact: ProviderFact,
        source: AssetSource,
        repository: Repository,
    ) -> Decision:
        content_evidence = self._get_content_evidence(fact)

        if content_evidence is None:
            return self._content_evidence_required()

        current_blob = self._require_current_blob(
            source=source,
            repository=repository,
        )
        return self._match_verified_existing_content(
            fact=fact,
            source=source,
            repository=repository,
            current_blob=current_blob,
            content_evidence=content_evidence,
            same_version=False,
        )

    @staticmethod
    def _content_evidence_required() -> Decision:
        return Decision(
            actions=[],
            requirements=[
                RequirementType.CONTENT_EVIDENCE,
            ],
            reason="content_evidence_required",
            confidence=0.0,
        )

    @staticmethod
    def _require_current_blob(
        *,
        source: AssetSource,
        repository: Repository,
    ) -> Blob:
        if source.blob_id is None:
            raise ContentEvidencePolicyError(
                "Existing Source has no Blob"
            )

        current_blob = repository.get_blob(source.blob_id)

        if current_blob is None:
            raise ContentEvidencePolicyError(
                "Existing Source Blob was not found"
            )

        if current_blob.asset_id is None:
            raise ContentEvidencePolicyError(
                "Existing Blob has no Asset"
            )

        return current_blob

    @classmethod
    def _same_version_requires_content_evidence(
        cls,
        *,
        fact: ProviderFact,
        source: AssetSource,
        current_blob: Blob,
    ) -> bool:
        incoming_size = cls._get_optional_provider_size_attribute(
            fact,
            "size",
        )

        if source.provider_size != incoming_size:
            return not (
                source.provider_size is None
                and incoming_size is not None
                and current_blob.size == incoming_size
            )

        return (
            incoming_size is not None
            and current_blob.size != incoming_size
        )

    @classmethod
    def _match_verified_existing_content(
        cls,
        *,
        fact: ProviderFact,
        source: AssetSource,
        repository: Repository,
        current_blob: Blob,
        content_evidence: ContentEvidence,
        same_version: bool,
    ) -> Decision:
        if current_blob.hash == content_evidence.sha256:
            cls._require_blob_matches_content_evidence(
                current_blob,
                content_evidence,
                allow_legacy_unknown_size=True,
            )
            if same_version and cls._source_state_is_unchanged(
                fact=fact,
                source=source,
            ):
                return Decision(
                    actions=[],
                    reason="source_content_verified_unchanged",
                    confidence=1.0,
                )

            updated_source = cls._updated_source(
                source=source,
                fact=fact,
                blob_id=current_blob.id,
            )
            return Decision(
                actions=[
                    Action(
                        type=ActionType.UPDATE_SOURCE,
                        source=updated_source,
                    ),
                ],
                reason=(
                    "source_content_verified_unchanged"
                    if (
                        same_version
                        and cls._same_version_requires_content_evidence(
                            fact=fact,
                            source=source,
                            current_blob=current_blob,
                        )
                    )
                    else (
                        "source_metadata_changed"
                        if same_version
                        else "source_returned_to_existing_blob_in_asset"
                    )
                ),
                confidence=1.0,
            )

        if current_blob.asset_id is None:
            raise ContentEvidencePolicyError(
                "Existing Blob has no Asset"
            )

        existing_blob_in_asset = repository.find_blob_by_hash_in_asset(
            content_hash=content_evidence.sha256,
            asset_id=current_blob.asset_id,
        )

        if existing_blob_in_asset is not None:
            cls._require_blob_matches_content_evidence(
                existing_blob_in_asset,
                content_evidence,
                allow_legacy_unknown_size=True,
            )
            updated_source = cls._updated_source(
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
                reason=(
                    "source_content_changed_same_version_reused_blob"
                    if same_version
                    else "source_returned_to_existing_blob_in_asset"
                ),
                confidence=1.0,
            )

        new_blob = cls._build_blob(
            fact=fact,
            asset_id=current_blob.asset_id,
            content_evidence=content_evidence,
        )
        updated_source = cls._updated_source(
            source=source,
            fact=fact,
            blob_id=new_blob.id,
        )
        return Decision(
            actions=[
                Action(type=ActionType.CREATE_BLOB, blob=new_blob),
                Action(type=ActionType.UPDATE_SOURCE, source=updated_source),
            ],
            reason=(
                "source_content_changed_same_version_new_blob"
                if same_version
                else "new_blob_for_existing_asset"
            ),
            confidence=1.0,
        )

    @classmethod
    def _get_content_evidence(
        cls,
        fact: ProviderFact,
    ) -> ContentEvidence | None:
        content_hash = fact.attributes.get("content_hash")
        content_byte_length = fact.attributes.get("content_byte_length")

        if content_hash is None and content_byte_length is None:
            return None

        try:
            content_evidence = ContentEvidence(
                sha256=content_hash,
                byte_length=content_byte_length,
            )
        except ValueError as error:
            raise ContentEvidencePolicyError(
                "Transient content evidence is incomplete or invalid"
            ) from error

        if content_evidence.byte_length > POSTGRES_BIGINT_MAX:
            raise ContentEvidenceSizeOverflowError(
                "Content byte length exceeds PostgreSQL BIGINT"
            )

        provider_size = cls._get_optional_provider_size_attribute(
            fact,
            "size",
        )
        if (
            provider_size is not None
            and provider_size != content_evidence.byte_length
        ):
            raise ProviderContentSizeMismatchError(
                provider=fact.provider,
                provider_size=provider_size,
                content_byte_length=content_evidence.byte_length,
            )

        return content_evidence

    @staticmethod
    def _require_blob_matches_content_evidence(
        blob: Blob,
        content_evidence: ContentEvidence,
        *,
        allow_legacy_unknown_size: bool,
    ) -> None:
        if (
            blob.hash != content_evidence.sha256
            or (
                blob.size != content_evidence.byte_length
                and not (
                    allow_legacy_unknown_size
                    and blob.size is None
                )
            )
        ):
            raise BlobContentEvidenceInvariantError(
                "Existing Blob does not match same-content evidence"
            )

    @staticmethod
    def _validate_fact(
        fact: ProviderFact,
    ) -> str | None:
        if not fact.provider.strip():
            return "invalid_fact_missing_provider"

        if not fact.external_id:
            return "invalid_fact_missing_external_id"

        if fact.kind not in {"file", "folder", "message"}:
            return "invalid_fact_kind"

        return None

    @staticmethod
    def _require_matching_resource_type(
        *,
        fact: ProviderFact,
        source: AssetSource,
        repository: Repository,
    ) -> None:
        if source.blob_id is None:
            raise RuntimeError("existing_source_has_no_blob")
        blob = repository.get_blob(source.blob_id)
        if blob is None or blob.asset_id is None:
            raise RuntimeError("existing_source_resource_not_found")
        asset = repository.get_asset(blob.asset_id)
        if asset is None:
            raise RuntimeError("existing_source_resource_not_found")
        if asset.resource_type.value != fact.kind:
            raise RuntimeError("existing_source_resource_type_mismatch")

    @staticmethod
    def _get_string_attribute(
        fact: ProviderFact,
        key: str,
    ) -> str | None:
        value = fact.attributes.get(key)

        if isinstance(value, str) and value:
            return value

        return None

    @classmethod
    def _source_state_is_unchanged(
        cls,
        fact: ProviderFact,
        source: AssetSource,
    ) -> bool:
        return (
            source.is_active
            and source.deleted_at is None
            and source.path == cls._get_optional_string_attribute(
                fact,
                "path",
            )
            and source.name == fact.name
            and source.version_tag
            == cls._get_optional_string_attribute(
                fact,
                "version_tag",
            )
            and source.provider_mime_type
            == cls._get_optional_string_attribute(
                fact,
                "mime_type",
            )
            and source.provider_size
            == cls._get_optional_provider_size_attribute(
                fact,
                "size",
            )
            and source.metadata
            == cls._build_source_metadata(fact)
        )

    @classmethod
    def _build_source(
        cls,
        fact: ProviderFact,
        blob_id: str,
    ) -> AssetSource:
        return AssetSource(
            blob_id=blob_id,
            provider=fact.provider,
            external_id=fact.external_id,
            path=cls._get_optional_string_attribute(
                fact,
                "path",
            ),
            name=fact.name,
            version_tag=cls._get_optional_string_attribute(
                fact,
                "version_tag",
            ),
            provider_mime_type=cls._get_optional_string_attribute(
                fact,
                "mime_type",
            ),
            provider_size=cls._get_optional_provider_size_attribute(
                fact,
                "size",
            ),
            metadata=cls._build_source_metadata(fact),
        )

    @classmethod
    def _updated_source(
        cls,
        source: AssetSource,
        fact: ProviderFact,
        blob_id: str | None,
    ) -> AssetSource:
        return replace(
            source,
            is_active=True,
            deleted_at=None,
            blob_id=blob_id,
            path=cls._get_optional_string_attribute(
                fact,
                "path",
            ),
            name=fact.name,
            version_tag=cls._get_optional_string_attribute(
                fact,
                "version_tag",
            ),
            provider_mime_type=cls._get_optional_string_attribute(
                fact,
                "mime_type",
            ),
            provider_size=cls._get_optional_provider_size_attribute(
                fact,
                "size",
            ),
            metadata=cls._build_source_metadata(fact),
        )

    @staticmethod
    def _build_source_metadata(
        fact: ProviderFact,
    ) -> dict:
        """
        保存 Provider 提供的原始附加信息。

        content_hash 是 PDI 在同步过程中计算出的临时补充信息，
        不属于 Provider 原始状态，因此不写入 Source metadata。
        """
        return dict(fact.raw)

    @staticmethod
    def _get_optional_string_attribute(
        fact: ProviderFact,
        key: str,
    ) -> str | None:
        value = fact.attributes.get(key)

        if isinstance(value, str):
            return value

        return None

    @staticmethod
    def _get_optional_provider_size_attribute(
        fact: ProviderFact,
        key: str,
    ) -> int | None:
        return validate_provider_size(fact.attributes.get(key))

    @staticmethod
    def _build_blob(
        fact: ProviderFact,
        asset_id: str,
        content_evidence: ContentEvidence,
    ) -> Blob:
        mime_type = fact.attributes.get("mime_type")

        if not isinstance(mime_type, str):
            mime_type = None

        return Blob(
            asset_id=asset_id,
            hash=content_evidence.sha256,
            size=content_evidence.byte_length,
            mime_type=mime_type,
        )

    @staticmethod
    def _build_asset_title(
        fact: ProviderFact,
    ) -> str:
        if not fact.name:
            return "Untitled Asset"

        if fact.kind == ResourceType.MESSAGE:
            return fact.name

        suffix = Path(fact.name).suffix

        if suffix:
            return fact.name.removesuffix(suffix)

        return fact.name

    def deactivate_source(
        self,
        source: AssetSource,
    ) -> Decision:
        source.is_active = False
        source.deleted_at = datetime.now(UTC)

        return Decision(
            actions=[
                Action(
                    type=ActionType.DEACTIVATE_SOURCE,
                    source=source,
                )
            ]
        )
