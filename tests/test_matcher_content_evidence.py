import hashlib

import pytest

from pdi.adapters.base import ProviderFact, ProviderResourceDisappearedError
from pdi.decision import ActionType, Decision, RequirementType
from pdi.engine import IncompleteProviderSyncError, SyncEngine
from pdi.identity import (
    BlobContentEvidenceInvariantError,
    ContentEvidenceSizeOverflowError,
    Matcher,
    ProviderContentSizeMismatchError,
)
from pdi.models import Asset, AssetSource, Blob
from pdi.models.asset_source import POSTGRES_BIGINT_MAX
from pdi.repository import InMemoryRepository


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _fact(
    *,
    external_id: str = "resource-1",
    version_tag: str = "v1",
    provider_size: int | None = 4,
    provider_mime_type: str = "text/plain",
    content: bytes | None = None,
) -> ProviderFact:
    attributes: dict[str, object] = {
        "path": f"{external_id}.txt",
        "size": provider_size,
        "mime_type": provider_mime_type,
        "version_tag": version_tag,
    }
    if content is not None:
        attributes.update(
            content_hash=_digest(content),
            content_byte_length=len(content),
        )
    return ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id=external_id,
        name=f"{external_id}.txt",
        attributes=attributes,
        raw={},
    )


def _seed(
    repository: InMemoryRepository,
    *,
    content: bytes = b"data",
    source_provider_size: int | None = 4,
    source_provider_mime_type: str | None = "text/plain",
) -> tuple[AssetSource, Blob]:
    asset = Asset(title="Seed")
    blob = Blob(
        asset_id=asset.id,
        hash=_digest(content),
        size=len(content),
        mime_type="text/plain",
    )
    source = AssetSource(
        blob_id=blob.id,
        provider="nextcloud",
        external_id="resource-1",
        path="resource-1.txt",
        name="resource-1.txt",
        version_tag="v1",
        provider_mime_type=source_provider_mime_type,
        provider_size=source_provider_size,
    )
    repository.assets[asset.id] = asset
    repository.blobs[blob.id] = blob
    repository.sources[source.id] = source
    return source, blob


def test_new_blob_hash_and_size_come_from_same_content_evidence() -> None:
    repository = InMemoryRepository()
    content = b"actual-content"
    fact = _fact(
        provider_size=len(content),
        provider_mime_type="text/markdown",
        content=content,
    )

    decision = Matcher().match(fact, repository)

    blob = decision.actions[1].blob
    source = decision.actions[2].source
    assert blob is not None
    assert source is not None
    assert blob.hash == _digest(content)
    assert blob.size == len(content)
    assert source.provider_size == len(content)
    assert source.provider_mime_type == "text/markdown"


def test_provider_size_must_match_streamed_content_evidence() -> None:
    repository = InMemoryRepository()
    fact = _fact(provider_size=100, content=b"x" * 101)

    with pytest.raises(ProviderContentSizeMismatchError) as raised:
        Matcher().match(fact, repository)

    assert raised.value.provider_size == 100
    assert raised.value.content_byte_length == 101
    assert repository.blobs == {}
    assert repository.sources == {}


def test_same_version_mime_only_drift_updates_source_without_evidence() -> None:
    repository = InMemoryRepository()
    _, blob = _seed(repository)
    fact = _fact(provider_mime_type="text/markdown")

    decision = Matcher().match(fact, repository)

    assert decision.requirements == []
    assert decision.reason == "source_metadata_changed"
    assert [action.type for action in decision.actions] == [
        ActionType.UPDATE_SOURCE
    ]
    assert decision.actions[0].source.provider_mime_type == "text/markdown"
    assert repository.blobs[blob.id] == blob


def test_same_version_non_null_size_drift_requires_content_evidence() -> None:
    repository = InMemoryRepository()
    _seed(repository, source_provider_size=3)

    decision = Matcher().match(_fact(provider_size=4), repository)

    assert decision.requirements == [RequirementType.CONTENT_EVIDENCE]
    assert decision.actions == []


def test_legacy_null_size_equal_to_blob_populates_without_evidence() -> None:
    repository = InMemoryRepository()
    _, blob = _seed(
        repository,
        source_provider_size=None,
        source_provider_mime_type=None,
    )

    decision = Matcher().match(_fact(provider_size=4), repository)

    assert decision.requirements == []
    assert decision.reason == "source_metadata_changed"
    assert decision.actions[0].source.provider_size == 4
    assert repository.blobs[blob.id] == blob


def test_legacy_null_size_different_from_blob_requires_evidence() -> None:
    repository = InMemoryRepository()
    _seed(repository, source_provider_size=None)

    decision = Matcher().match(_fact(provider_size=5), repository)

    assert decision.requirements == [RequirementType.CONTENT_EVIDENCE]
    assert decision.actions == []


def test_source_size_equal_but_blob_size_different_requires_evidence() -> None:
    repository = InMemoryRepository()
    _, blob = _seed(repository, source_provider_size=4)
    blob.size = 3

    decision = Matcher().match(_fact(provider_size=4), repository)

    assert decision.requirements == [RequirementType.CONTENT_EVIDENCE]


def test_size_drift_verified_unchanged_updates_source_only() -> None:
    repository = InMemoryRepository()
    _, blob = _seed(repository, source_provider_size=3)
    fact = _fact(provider_size=4, content=b"data")

    decision = Matcher().match(fact, repository)

    assert decision.reason == "source_content_verified_unchanged"
    assert [action.type for action in decision.actions] == [
        ActionType.UPDATE_SOURCE
    ]
    assert decision.actions[0].source.blob_id == blob.id
    assert decision.actions[0].source.provider_size == 4
    assert repository.blobs[blob.id] == blob


def test_same_version_verified_changed_content_creates_blob() -> None:
    repository = InMemoryRepository()
    _, old_blob = _seed(repository, source_provider_size=4)
    changed = b"changed"
    fact = _fact(provider_size=len(changed), content=changed)

    decision = Matcher().match(fact, repository)

    assert decision.reason == "source_content_changed_same_version_new_blob"
    assert [action.type for action in decision.actions] == [
        ActionType.CREATE_BLOB,
        ActionType.UPDATE_SOURCE,
    ]
    new_blob = decision.actions[0].blob
    assert new_blob is not None
    assert new_blob.asset_id == old_blob.asset_id
    assert new_blob.hash == _digest(changed)
    assert new_blob.size == len(changed)


def test_same_version_verified_changed_content_reuses_blob_in_asset() -> None:
    repository = InMemoryRepository()
    _, old_blob = _seed(repository, source_provider_size=4)
    returned_content = b"prior-version"
    returned_blob = Blob(
        asset_id=old_blob.asset_id,
        hash=_digest(returned_content),
        size=len(returned_content),
        mime_type="text/plain",
    )
    repository.blobs[returned_blob.id] = returned_blob
    fact = _fact(
        provider_size=len(returned_content),
        content=returned_content,
    )

    decision = Matcher().match(fact, repository)

    assert decision.reason == "source_content_changed_same_version_reused_blob"
    assert [action.type for action in decision.actions] == [
        ActionType.UPDATE_SOURCE
    ]
    assert decision.actions[0].source.blob_id == returned_blob.id
    assert repository.blobs[old_blob.id] == old_blob
    assert repository.blobs[returned_blob.id] == returned_blob


def test_same_hash_with_different_stored_blob_length_fails_closed() -> None:
    repository = InMemoryRepository()
    _, blob = _seed(repository, content=b"data", source_provider_size=4)
    blob.size = 3
    fact = _fact(provider_size=4, content=b"data")

    with pytest.raises(BlobContentEvidenceInvariantError):
        Matcher().match(fact, repository)

    assert repository.blobs[blob.id] is blob
    assert blob.size == 3


def test_legacy_unknown_blob_size_can_reuse_matching_content_without_mutation(
) -> None:
    repository = InMemoryRepository()
    source, blob = _seed(
        repository,
        content=b"message",
        source_provider_size=None,
    )
    blob.size = None
    source.version_tag = "prior-content-hash"
    fact = _fact(
        version_tag="v2",
        provider_size=None,
        content=b"message",
    )

    decision = Matcher().match(fact, repository)

    assert decision.reason == "source_returned_to_existing_blob_in_asset"
    assert decision.actions[0].source.blob_id == blob.id
    assert blob.size is None


def test_version_changed_same_hash_reuses_current_blob() -> None:
    repository = InMemoryRepository()
    _, blob = _seed(repository)
    fact = _fact(version_tag="v2", content=b"data")

    decision = Matcher().match(fact, repository)

    assert decision.reason == "source_returned_to_existing_blob_in_asset"
    assert [action.type for action in decision.actions] == [
        ActionType.UPDATE_SOURCE
    ]
    assert decision.actions[0].source.blob_id == blob.id


def test_version_changed_new_hash_uses_evidence_length_not_old_size() -> None:
    repository = InMemoryRepository()
    _seed(repository)
    content = b"new-content"
    fact = _fact(
        version_tag="v2",
        provider_size=len(content),
        content=content,
    )

    decision = Matcher().match(fact, repository)

    new_blob = decision.actions[0].blob
    assert new_blob is not None
    assert new_blob.hash == _digest(content)
    assert new_blob.size == len(content)


def test_new_source_global_blob_reuse_checks_size_and_preserves_observations(
) -> None:
    repository = InMemoryRepository()
    _, shared_blob = _seed(repository)
    fact = _fact(
        external_id="resource-2",
        provider_size=4,
        provider_mime_type="text/markdown",
        content=b"data",
    )

    decision = Matcher().match(fact, repository)

    assert decision.reason == "new_source_existing_blob"
    source = decision.actions[0].source
    assert source is not None
    assert source.blob_id == shared_blob.id
    assert source.provider_size == 4
    assert source.provider_mime_type == "text/markdown"
    assert repository.blobs[shared_blob.id] == shared_blob


def test_new_source_global_same_hash_with_different_size_fails_closed() -> None:
    repository = InMemoryRepository()
    _, shared_blob = _seed(repository)
    fact = _fact(
        external_id="resource-2",
        provider_size=None,
    )
    fact.attributes.update(
        content_hash=shared_blob.hash,
        content_byte_length=5,
    )

    with pytest.raises(BlobContentEvidenceInvariantError):
        Matcher().match(fact, repository)

    assert len(repository.blobs) == 1
    assert repository.blobs[shared_blob.id] == shared_blob
    assert repository.find_source("nextcloud", "resource-2") is None


def test_new_source_cannot_reuse_global_blob_with_unknown_legacy_size() -> None:
    repository = InMemoryRepository()
    _, shared_blob = _seed(repository)
    shared_blob.size = None
    fact = _fact(
        external_id="resource-2",
        provider_size=4,
        content=b"data",
    )

    with pytest.raises(BlobContentEvidenceInvariantError):
        Matcher().match(fact, repository)

    assert len(repository.blobs) == 1
    assert repository.blobs[shared_blob.id].size is None
    assert repository.find_source("nextcloud", "resource-2") is None


def test_content_evidence_over_bigint_fails_before_persistence() -> None:
    repository = InMemoryRepository()
    fact = _fact(provider_size=None)
    fact.attributes.update(
        content_hash=_digest(b"oversized"),
        content_byte_length=POSTGRES_BIGINT_MAX + 1,
    )

    with pytest.raises(ContentEvidenceSizeOverflowError):
        Matcher().match(fact, repository)

    assert repository.blobs == {}
    assert repository.sources == {}


class _OneFactAdapter:
    provider_name = "nextcloud"

    def __init__(
        self,
        fact: ProviderFact,
        content: bytes,
        *,
        disappear: bool = False,
    ) -> None:
        self.fact = fact
        self.content = content
        self.disappear = disappear
        self.open_count = 0

    def connect(self) -> None:
        return None

    def scan(self) -> tuple[ProviderFact, ...]:
        return (self.fact,)

    def open(self, fact: ProviderFact):
        self.open_count += 1
        if self.disappear:
            raise ProviderResourceDisappearedError(self.provider_name)
        yield self.content


def test_sync_engine_computes_evidence_once_and_sets_transient_fields() -> None:
    repository = InMemoryRepository()
    content = b"streamed"
    fact = _fact(provider_size=len(content))
    adapter = _OneFactAdapter(fact, content)

    SyncEngine(adapter, Matcher(), repository).sync_once()

    assert adapter.open_count == 1
    assert fact.attributes["content_hash"] == _digest(content)
    assert fact.attributes["content_byte_length"] == len(content)
    blob = next(iter(repository.blobs.values()))
    assert blob.hash == _digest(content)
    assert blob.size == len(content)


def test_provider_size_mismatch_aborts_before_missing_reconciliation() -> None:
    repository = InMemoryRepository()
    missing, _ = _seed(repository)
    fact = _fact(
        external_id="new-resource",
        provider_size=100,
    )
    adapter = _OneFactAdapter(fact, b"x" * 101)

    with pytest.raises(ProviderContentSizeMismatchError):
        SyncEngine(adapter, Matcher(), repository).sync_once()

    assert adapter.open_count == 1
    assert missing.is_active is True
    assert repository.find_source("nextcloud", "new-resource") is None


def test_disappeared_during_evidence_keeps_reconciliation_disabled() -> None:
    repository = InMemoryRepository()
    missing, _ = _seed(repository)
    fact = _fact(external_id="new-resource")
    adapter = _OneFactAdapter(fact, b"data", disappear=True)

    with pytest.raises(IncompleteProviderSyncError):
        SyncEngine(adapter, Matcher(), repository).sync_once()

    assert adapter.open_count == 1
    assert missing.is_active is True


class _RepeatingEvidenceMatcher:
    def match(self, fact: ProviderFact, repository: InMemoryRepository) -> Decision:
        return Decision(requirements=[RequirementType.CONTENT_EVIDENCE])

    def deactivate_source(self, source: AssetSource) -> Decision:
        raise AssertionError("missing reconciliation must not run")


def test_unsatisfied_evidence_requirement_never_redownloads() -> None:
    repository = InMemoryRepository()
    fact = _fact()
    adapter = _OneFactAdapter(fact, b"data")

    with pytest.raises(
        RuntimeError,
        match="remained after one Provider body read",
    ):
        SyncEngine(adapter, _RepeatingEvidenceMatcher(), repository).sync_once()

    assert adapter.open_count == 1


class _LegacyHashRequirementMatcher:
    def match(
        self,
        fact: ProviderFact,
        repository: InMemoryRepository,
    ) -> Decision:
        if fact.attributes.get("content_hash") is None:
            return Decision(requirements=[RequirementType.CONTENT_HASH])
        assert fact.attributes["content_byte_length"] == 4
        return Decision(reason="legacy_hash_requirement_satisfied")

    def deactivate_source(self, source: AssetSource) -> Decision:
        return Decision()


def test_legacy_content_hash_requirement_uses_same_single_evidence_read(
) -> None:
    repository = InMemoryRepository()
    fact = _fact()
    adapter = _OneFactAdapter(fact, b"data")

    SyncEngine(
        adapter,
        _LegacyHashRequirementMatcher(),
        repository,
    ).sync_once()

    assert adapter.open_count == 1
    assert fact.attributes["content_hash"] == _digest(b"data")
    assert fact.attributes["content_byte_length"] == 4
