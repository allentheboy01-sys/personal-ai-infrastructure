from pdi.adapters.base import ProviderFact
from pdi.decision import ActionType
from pdi.identity import Matcher
from pdi.models import Asset, AssetSource, Blob
from pdi.repository import InMemoryRepository


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
            "content_hash": "hash-aaa",
        },
        raw={},
    )

    decision = matcher.match(
        fact=fact,
        repository=repository,
    )

    assert decision.reason == "new_source_new_blob"

    assert [
        action.type
        for action in decision.actions
    ] == [
        ActionType.CREATE_ASSET,
        ActionType.CREATE_BLOB,
        ActionType.CREATE_SOURCE,
    ]

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
            "content_hash": "hash-aaa",
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

    assert second_decision.reason == "source_unchanged"
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
            "content_hash": "hash-aaa",
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
            "content_hash": "hash-aaa",
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
            "content_hash": "hash-aaa",
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
            "content_hash": "hash-bbb",
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
    assert blob.hash == "hash-bbb"

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
            "mime_type": "application/pdf",
            "modified_at": None,
            "version_tag": "nextcloud-v1",
            "content_hash": "hash-aaa",
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
            "mime_type": "application/pdf",
            "modified_at": None,
            "version_tag": "google-v1",
            "content_hash": "hash-aaa",
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

    assert len(repository.assets) == 1
    assert len(repository.blobs) == 1
    assert len(repository.sources) == 2

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
            "content_hash": "hash-aaa",
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
            "content_hash": "hash-bbb",
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
            "content_hash": "hash-bbb",
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

    assert blob_a_after.hash == "hash-bbb"
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
            "content_hash": "hash-metadata",
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