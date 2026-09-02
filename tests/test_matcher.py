import hashlib

import pytest

from pdi.adapters.base import ProviderFact
from pdi.decision import ActionType, RequirementType
from pdi.identity import (
    BlobContentEvidenceInvariantError,
    ContentEvidenceSizeOverflowError,
    Matcher,
    ProviderContentSizeMismatchError,
)
from pdi.models import Asset, AssetSource, Blob, ResourceType
from pdi.models.asset_source import POSTGRES_BIGINT_MAX
from pdi.repository import InMemoryRepository


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _content_evidence(label: str, byte_length: int) -> dict[str, object]:
    return {
        "content_hash": _digest(label),
        "content_byte_length": byte_length,
    }


def test_create_new_asset():
    repository = InMemoryRepository()
    matcher = Matcher()

    fact = ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id="test-file",
        name="毕业论文.pdf",
        attributes={
            "path": "Documents/毕业论文.pdf",
            "size": 1024,
            "mime_type": "application/pdf",
            "modified_at": None,
            "version_tag": "v1",
            **_content_evidence("hash-aaa", 1024),
        },
        raw={},
    )

    decision = matcher.match(
        fact=fact,
        repository=repository,
    )

    assert decision.reason == "new_source_new_blob"
    assert decision.actions[0].asset.resource_type is ResourceType.FILE

    assert [
        action.type
        for action in decision.actions
    ] == [
        ActionType.CREATE_ASSET,
        ActionType.CREATE_BLOB,
        ActionType.CREATE_SOURCE,
    ]
    created_source = decision.actions[2].source
    assert created_source is not None
    assert created_source.provider_mime_type == "application/pdf"
    assert created_source.provider_size == 1024


@pytest.mark.parametrize(
    "invalid_size",
    [True, -1, POSTGRES_BIGINT_MAX + 1, 1.5, "1"],
)
def test_invalid_provider_size_cannot_reach_new_blob_or_source(
    invalid_size: object,
) -> None:
    repository = InMemoryRepository()
    fact = ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id="invalid-size",
        name="invalid-size.txt",
        attributes={
            "path": "invalid-size.txt",
            "size": invalid_size,
            "mime_type": "text/plain",
            "version_tag": "v1",
            **_content_evidence("invalid-size-hash", 0),
        },
        raw={},
    )

    with pytest.raises(ValueError, match="provider_size"):
        Matcher().match(fact, repository)

    assert repository.blobs == {}
    assert repository.sources == {}


@pytest.mark.parametrize(
    "valid_size",
    [None, 0, POSTGRES_BIGINT_MAX],
)
def test_valid_provider_size_reaches_new_blob_and_source(
    valid_size: int | None,
) -> None:
    repository = InMemoryRepository()
    fact = ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id="valid-size",
        name="valid-size.txt",
        attributes={
            "path": "valid-size.txt",
            "size": valid_size,
            "mime_type": "text/plain",
            "version_tag": "v1",
            **_content_evidence(
                "valid-size-hash",
                0 if valid_size is None else valid_size,
            ),
        },
        raw={},
    )

    decision = Matcher().match(fact, repository)

    created_blob = decision.actions[1].blob
    created_source = decision.actions[2].source
    assert created_blob is not None
    assert created_source is not None
    assert created_blob.size == (0 if valid_size is None else valid_size)
    assert created_source.provider_size == valid_size


def _message_fact(
    external_id: str,
    *,
    content_hash: str = "same-raw-hash",
    version_tag: str = "immutable-message",
) -> ProviderFact:
    return ProviderFact(
        provider="gmail",
        kind="message",
        external_id=external_id,
        name=None,
        attributes={
            **_content_evidence(content_hash, 128),
            "mime_type": "message/rfc822",
            "size": 128,
            "version_tag": version_tag,
        },
        raw={},
    )


def test_distinct_messages_with_same_content_remain_distinct_resources():
    repository = InMemoryRepository()
    matcher = Matcher()

    for external_id in ("message-a", "message-b"):
        decision = matcher.match(
            fact=_message_fact(external_id),
            repository=repository,
        )
        assert decision.reason == "new_message_source"
        repository.execute(decision)

    assert len(repository.assets) == 2
    assert len(repository.blobs) == 2
    assert len(repository.sources) == 2
    assert {
        asset.resource_type for asset in repository.assets.values()
    } == {ResourceType.MESSAGE}
    assert len({blob.asset_id for blob in repository.blobs.values()}) == 2


def test_existing_message_preserves_resource_and_versions_inside_it():
    repository = InMemoryRepository()
    matcher = Matcher()
    original = _message_fact("message-a")
    repository.execute(matcher.match(original, repository))
    original_asset_id = next(iter(repository.assets))

    repeated = matcher.match(original, repository)
    assert repeated.reason == "source_content_verified_unchanged"
    assert repeated.actions == []

    changed = _message_fact(
        "message-a",
        content_hash="changed-raw-hash",
        version_tag="changed-message",
    )
    repository.execute(matcher.match(changed, repository))

    assert set(repository.assets) == {original_asset_id}
    assert len(repository.blobs) == 2
    assert {
        blob.asset_id for blob in repository.blobs.values()
    } == {original_asset_id}


def test_existing_source_kind_mismatch_fails_explicitly():
    repository = InMemoryRepository()
    matcher = Matcher()
    repository.execute(
        matcher.match(_message_fact("message-a"), repository)
    )

    mismatched = ProviderFact(
        provider="gmail",
        kind="file",
        external_id="message-a",
        name="message.eml",
        attributes={
            **_content_evidence("same-raw-hash", 128),
            "version_tag": "immutable-message",
        },
        raw={},
    )
    with pytest.raises(
        RuntimeError,
        match="existing_source_resource_type_mismatch",
    ):
        matcher.match(mismatched, repository)

def test_same_source_should_do_nothing():
    repository = InMemoryRepository()
    matcher = Matcher()

    fact = ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id="test-file",
        name="毕业论文.pdf",
        attributes={
            "path": "Documents/毕业论文.pdf",
            "size": 1024,
            "mime_type": "application/pdf",
            "modified_at": None,
            "version_tag": "v1",
            **_content_evidence("hash-aaa", 1024),
        },
        raw={},
    )

    first_decision = matcher.match(
        fact=fact,
        repository=repository,
    )

    repository.execute(first_decision)

    second_decision = matcher.match(
        fact=fact,
        repository=repository,
    )

    assert second_decision.reason == "source_content_verified_unchanged"
    assert second_decision.actions == []

    assert len(repository.assets) == 1
    assert len(repository.blobs) == 1
    assert len(repository.sources) == 1

def test_rename_should_only_update_source():
    repository = InMemoryRepository()
    matcher = Matcher()

    original_fact = ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id="test-file",
        name="毕业论文.pdf",
        attributes={
            "path": "Documents/毕业论文.pdf",
            "size": 1024,
            "mime_type": "application/pdf",
            "modified_at": None,
            "version_tag": "v1",
            **_content_evidence("hash-aaa", 1024),
        },
        raw={},
    )

    repository.execute(
        matcher.match(
            fact=original_fact,
            repository=repository,
        )
    )

    renamed_fact = ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id="test-file",
        name="毕业论文最终版.pdf",
        attributes={
            "path": "Archive/毕业论文最终版.pdf",
            "size": 1024,
            "mime_type": "application/pdf",
            "modified_at": None,
            "version_tag": "v1",
            **_content_evidence("hash-aaa", 1024),
        },
        raw={},
    )

    decision = matcher.match(
        fact=renamed_fact,
        repository=repository,
    )

    assert decision.reason == "source_metadata_changed"

    assert [
        action.type
        for action in decision.actions
    ] == [
        ActionType.UPDATE_SOURCE,
    ]

    repository.execute(decision)

    saved_source = repository.find_source(
        provider="nextcloud",
        external_id="test-file",
    )

    assert saved_source is not None
    assert saved_source.name == "毕业论文最终版.pdf"
    assert saved_source.path == "Archive/毕业论文最终版.pdf"
    assert saved_source.version_tag == "v1"

    assert len(repository.assets) == 1
    assert len(repository.blobs) == 1
    assert len(repository.sources) == 1

def test_content_change_should_create_new_blob():
    repository = InMemoryRepository()
    matcher = Matcher()

    original_fact = ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id="test-file",
        name="毕业论文.pdf",
        attributes={
            "path": "Documents/毕业论文.pdf",
            "size": 1024,
            "mime_type": "application/pdf",
            "modified_at": None,
            "version_tag": "v1",
            **_content_evidence("hash-aaa", 1024),
        },
        raw={},
    )

    repository.execute(
        matcher.match(
            fact=original_fact,
            repository=repository,
        )
    )

    updated_fact = ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id="test-file",
        name="毕业论文.pdf",
        attributes={
            "path": "Documents/毕业论文.pdf",
            "size": 2048,
            "mime_type": "application/pdf",
            "modified_at": None,
            "version_tag": "v2",
            **_content_evidence("hash-bbb", 2048),
        },
        raw={},
    )

    decision = matcher.match(
        fact=updated_fact,
        repository=repository,
    )

    assert decision.reason == "new_blob_for_existing_asset"

    assert [
        action.type
        for action in decision.actions
    ] == [
        ActionType.CREATE_BLOB,
        ActionType.UPDATE_SOURCE,
    ]

    repository.execute(decision)

    source = repository.find_source(
        provider="nextcloud",
        external_id="test-file",
    )

    blob = repository.get_blob(source.blob_id)

    assert blob is not None
    assert blob.hash == _digest("hash-bbb")

    assert len(repository.assets) == 1
    assert len(repository.blobs) == 2
    assert len(repository.sources) == 1

def test_new_source_should_reuse_existing_blob():
    repository = InMemoryRepository()
    matcher = Matcher()

    first_fact = ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id="nextcloud-file",
        name="毕业论文.pdf",
        attributes={
            "path": "Documents/毕业论文.pdf",
            "size": 1024,
            "mime_type": "text/x-python",
            "modified_at": None,
            "version_tag": "nextcloud-v1",
            **_content_evidence("hash-aaa", 1024),
        },
        raw={},
    )

    repository.execute(
        matcher.match(
            fact=first_fact,
            repository=repository,
        )
    )

    second_fact = ProviderFact(
        provider="google_drive",
        kind="file",
        external_id="google-file",
        name="thesis-copy.pdf",
        attributes={
            "path": None,
            "size": 1024,
            "mime_type": "text/markdown",
            "modified_at": None,
            "version_tag": "google-v1",
            **_content_evidence("hash-aaa", 1024),
        },
        raw={},
    )

    decision = matcher.match(
        fact=second_fact,
        repository=repository,
    )

    assert decision.reason == "new_source_existing_blob"

    assert [
        action.type
        for action in decision.actions
    ] == [
        ActionType.CREATE_SOURCE,
    ]

    repository.execute(decision)

    nextcloud_source = repository.find_source(
        provider="nextcloud",
        external_id="nextcloud-file",
    )

    google_source = repository.find_source(
        provider="google_drive",
        external_id="google-file",
    )

    assert nextcloud_source is not None
    assert google_source is not None

    assert nextcloud_source.blob_id == google_source.blob_id
    assert nextcloud_source.provider_mime_type == "text/x-python"
    assert nextcloud_source.provider_size == 1024
    assert google_source.provider_mime_type == "text/markdown"
    assert google_source.provider_size == 1024

    shared_blob = repository.get_blob(nextcloud_source.blob_id)
    assert shared_blob is not None
    assert shared_blob.mime_type == "text/x-python"

    assert len(repository.assets) == 1
    assert len(repository.blobs) == 1
    assert len(repository.sources) == 2


def test_same_version_provider_mime_change_updates_source_without_evidence(
) -> None:
    repository = InMemoryRepository()
    matcher = Matcher()
    fact = ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id="observed-file",
        name="observed.txt",
        attributes={
            "path": "observed.txt",
            "size": 1024,
            "mime_type": "text/plain",
            "version_tag": "v1",
            **_content_evidence("same-hash", 1024),
        },
        raw={},
    )
    repository.execute(matcher.match(fact, repository))
    original_blob = next(iter(repository.blobs.values()))
    changed = ProviderFact(
        provider=fact.provider,
        kind=fact.kind,
        external_id=fact.external_id,
        name=fact.name,
        attributes={
            key: value
            for key, value in fact.attributes.items()
            if key not in {"content_hash", "content_byte_length"}
        }
        | {"mime_type": "text/markdown"},
        raw=dict(fact.raw),
    )

    decision = matcher.match(changed, repository)

    assert decision.reason == "source_metadata_changed"
    assert decision.requirements == []
    assert [action.type for action in decision.actions] == [
        ActionType.UPDATE_SOURCE,
    ]
    updated_source = decision.actions[0].source
    assert updated_source is not None
    assert updated_source.blob_id == original_blob.id
    assert updated_source.provider_mime_type == "text/markdown"
    assert updated_source.provider_size == 1024
    assert repository.blobs[original_blob.id] == original_blob


def test_same_version_non_null_provider_size_drift_requires_evidence(
) -> None:
    repository = InMemoryRepository()
    matcher = Matcher()
    fact = ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id="observed-file",
        name="observed.txt",
        attributes={
            "path": "observed.txt",
            "size": 1024,
            "mime_type": "text/plain",
            "version_tag": "v1",
            **_content_evidence("same-hash", 1024),
        },
        raw={},
    )
    repository.execute(matcher.match(fact, repository))
    original_blob = next(iter(repository.blobs.values()))
    changed = ProviderFact(
        provider=fact.provider,
        kind=fact.kind,
        external_id=fact.external_id,
        name=fact.name,
        attributes={
            "path": "observed.txt",
            "size": 2048,
            "mime_type": "text/plain",
            "version_tag": "v1",
        },
        raw={},
    )

    decision = matcher.match(changed, repository)

    assert decision.reason == "content_evidence_required"
    assert decision.requirements == [RequirementType.CONTENT_EVIDENCE]
    assert decision.actions == []
    assert repository.blobs[original_blob.id] == original_blob


def test_legacy_null_source_first_observation_updates_source() -> None:
    repository = InMemoryRepository()
    matcher = Matcher()
    asset = Asset(title="Legacy Source")
    blob = Blob(
        asset_id=asset.id,
        hash="legacy-hash",
        size=32,
        mime_type="text/plain",
    )
    source = AssetSource(
        blob_id=blob.id,
        provider="nextcloud",
        external_id="legacy-source",
        path="legacy.txt",
        name="legacy.txt",
        version_tag="v1",
    )
    repository.assets[asset.id] = asset
    repository.blobs[blob.id] = blob
    repository.sources[source.id] = source
    fact = ProviderFact(
        provider=source.provider,
        kind="file",
        external_id=source.external_id,
        name=source.name,
        attributes={
            "path": source.path,
            "size": 32,
            "mime_type": "text/plain",
            "version_tag": source.version_tag,
        },
        raw={},
    )

    decision = matcher.match(fact, repository)

    assert decision.requirements == []
    assert decision.reason == "source_metadata_changed"
    assert [action.type for action in decision.actions] == [
        ActionType.UPDATE_SOURCE,
    ]
    updated_source = decision.actions[0].source
    assert updated_source is not None
    assert updated_source.provider_mime_type == "text/plain"
    assert updated_source.provider_size == 32
    assert repository.blobs[blob.id] == blob

def test_existing_source_should_not_jump_between_assets():
    repository = InMemoryRepository()
    matcher = Matcher()

    fact_a = ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id="file-a",
        name="A.pdf",
        attributes={
            "path": "A.pdf",
            "size": 100,
            "mime_type": "application/pdf",
            "modified_at": None,
            "version_tag": "a-v1",
            **_content_evidence("hash-aaa", 100),
        },
        raw={},
    )

    fact_b = ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id="file-b",
        name="B.pdf",
        attributes={
            "path": "B.pdf",
            "size": 200,
            "mime_type": "application/pdf",
            "modified_at": None,
            "version_tag": "b-v1",
            **_content_evidence("hash-bbb", 200),
        },
        raw={},
    )

    repository.execute(
        matcher.match(
            fact=fact_a,
            repository=repository,
        )
    )

    repository.execute(
        matcher.match(
            fact=fact_b,
            repository=repository,
        )
    )

    source_a_before = repository.find_source(
        provider="nextcloud",
        external_id="file-a",
    )

    source_b = repository.find_source(
        provider="nextcloud",
        external_id="file-b",
    )

    assert source_a_before is not None
    assert source_b is not None
    assert source_a_before.blob_id is not None
    assert source_b.blob_id is not None

    blob_a_before = repository.get_blob(
        source_a_before.blob_id,
    )

    blob_b = repository.get_blob(
        source_b.blob_id,
    )

    assert blob_a_before is not None
    assert blob_b is not None
    assert blob_a_before.asset_id is not None
    assert blob_b.asset_id is not None
    assert blob_a_before.asset_id != blob_b.asset_id

    updated_fact_a = ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id="file-a",
        name="A.pdf",
        attributes={
            "path": "A.pdf",
            "size": 200,
            "mime_type": "application/pdf",
            "modified_at": None,
            "version_tag": "a-v2",
            **_content_evidence("hash-bbb", 200),
        },
        raw={},
    )

    decision = matcher.match(
        fact=updated_fact_a,
        repository=repository,
    )

    assert decision.reason == "new_blob_for_existing_asset"

    assert [
        action.type
        for action in decision.actions
    ] == [
        ActionType.CREATE_BLOB,
        ActionType.UPDATE_SOURCE,
    ]

    repository.execute(decision)

    source_a_after = repository.find_source(
        provider="nextcloud",
        external_id="file-a",
    )

    assert source_a_after is not None
    assert source_a_after.blob_id is not None

    blob_a_after = repository.get_blob(
        source_a_after.blob_id,
    )

    assert blob_a_after is not None

    assert blob_a_after.hash == _digest("hash-bbb")
    assert blob_a_after.asset_id == blob_a_before.asset_id
    assert blob_a_after.asset_id != blob_b.asset_id
    assert blob_a_after.id != blob_b.id

    assert len(repository.assets) == 2
    assert len(repository.blobs) == 3
    assert len(repository.sources) == 2

def test_new_source_preserves_provider_raw_metadata() -> None:
    repository = InMemoryRepository()
    matcher = Matcher()

    fact = ProviderFact(
        provider="nextcloud",
        external_id="file-123",
        kind="file",
        name="metadata.txt",
        attributes={
            "path": "/docs/metadata.txt",
            "version_tag": "v1",
            **_content_evidence("hash-metadata", 128),
            "size": 128,
            "mime_type": "text/plain",
        },
        raw={
            "file_id": "123",
            "permissions": "RGDNVW",
        },
    )

    decision = matcher.match(
        fact=fact,
        repository=repository,
    )

    create_source_action = next(
        action
        for action in decision.actions
        if action.type == ActionType.CREATE_SOURCE
    )

    assert create_source_action.source is not None
    assert create_source_action.source.metadata == {
        "file_id": "123",
        "permissions": "RGDNVW",
    }

    # 验证保存的是新字典，而不是和 ProviderFact 共用同一对象。
    assert create_source_action.source.metadata is not fact.raw


def test_same_version_raw_metadata_change_updates_source() -> None:
    repository = InMemoryRepository()
    matcher = Matcher()

    asset = Asset(
        title="Metadata Update Test",
    )

    blob = Blob(
        asset_id=asset.id,
        hash="metadata-update-hash",
        size=128,
        mime_type="text/plain",
    )

    source = AssetSource(
        blob_id=blob.id,
        provider="nextcloud",
        external_id="file-456",
        path="/docs/metadata.txt",
        name="metadata.txt",
        version_tag="v1",
        metadata={
            "file_id": "456",
            "permissions": "RG",
        },
    )

    repository.assets[asset.id] = asset
    repository.blobs[blob.id] = blob
    repository.sources[source.id] = source

    fact = ProviderFact(
        provider="nextcloud",
        external_id="file-456",
        kind="file",
        name="metadata.txt",
        attributes={
            "path": "/docs/metadata.txt",
            "version_tag": "v1",
            "size": 128,
            "mime_type": "text/plain",
        },
        raw={
            "file_id": "456",
            "permissions": "RGDNVW",
        },
    )

    decision = matcher.match(
        fact=fact,
        repository=repository,
    )

    assert decision.reason == "source_metadata_changed"
    assert len(decision.actions) == 1
    assert decision.actions[0].type == ActionType.UPDATE_SOURCE

    updated_source = decision.actions[0].source

    assert updated_source is not None
    assert updated_source.id == source.id
    assert updated_source.blob_id == blob.id
    assert updated_source.path == source.path
    assert updated_source.name == source.name
    assert updated_source.version_tag == source.version_tag
    assert updated_source.metadata == {
        "file_id": "456",
        "permissions": "RGDNVW",
    }

    # Matcher 只生成 Decision，不应直接修改 Repository 中的旧对象。
    assert repository.sources[source.id].metadata == {
        "file_id": "456",
        "permissions": "RG",
    }

def test_deactivate_source() -> None:
    matcher = Matcher()

    source = AssetSource(
        blob_id="blob-1",
        provider="nextcloud",
        external_id="123",
        path="/test.txt",
        name="test.txt",
        version_tag="v1",
    )

    decision = matcher.deactivate_source(source)

    assert len(decision.actions) == 1

    action = decision.actions[0]

    assert action.type == ActionType.DEACTIVATE_SOURCE
    assert action.source is source
    assert source.is_active is False
    assert source.deleted_at is not None
