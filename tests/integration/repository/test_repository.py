from pdi.database import create_postgres_engine
from pdi.decision import Action, ActionType, Decision
from pdi.models import Asset, AssetSource, Blob
from pdi.repository import PostgreSQLRepository
from tests.integration.database_guard import (
    require_safe_test_database_url,
)
from datetime import UTC, datetime


def create_test_engine():
    return create_postgres_engine(
        require_safe_test_database_url(),
    )

def test_connection():
    engine = create_test_engine()
    repo = PostgreSQLRepository(engine)

    assert repo.test_connection()

    engine.dispose()

def test_execute_create_complete_asset_chain() -> None:
    engine = create_test_engine()

    repository = PostgreSQLRepository(engine)

    # Arrange：创建一套彼此关联的领域对象
    asset = Asset(
        title="Repository Integration Test",
        metadata={
            "test": True,
        },
    )

    blob = Blob(
        asset_id=asset.id,
        hash=f"test-hash-{asset.id}",
        size=1024,
        mime_type="text/plain",
    )

    source = AssetSource(
        blob_id=blob.id,
        provider="integration-test",
        external_id=f"source-{asset.id}",
        path="/tests/repository.txt",
        name="repository.txt",
        version_tag="v1",
        metadata={
            "test": True,
        },
    )

    decision = Decision(
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
    )

    # Act：把整个 Decision 作为一个事务写入数据库
    repository.execute(decision)

    # Assert：重新从数据库读回 Domain Model
    stored_asset = repository.get_asset(asset.id)
    stored_blob = repository.get_blob(blob.id)
    stored_source = repository.find_source(
        provider=source.provider,
        external_id=source.external_id,
    )

    assert stored_asset is not None
    assert stored_asset.id == asset.id
    assert stored_asset.title == asset.title
    assert stored_asset.metadata == asset.metadata

    assert stored_blob is not None
    assert stored_blob.id == blob.id
    assert stored_blob.asset_id == asset.id
    assert stored_blob.hash == blob.hash
    assert stored_blob.size == blob.size
    assert stored_blob.mime_type == blob.mime_type

    assert stored_source is not None
    assert stored_source.id == source.id
    assert stored_source.blob_id == blob.id
    assert stored_source.provider == source.provider
    assert stored_source.external_id == source.external_id
    assert stored_source.path == source.path
    assert stored_source.name == source.name
    assert stored_source.version_tag == source.version_tag
    assert stored_source.metadata == source.metadata

    # 同时验证另外两个 Hash 查询
    assert repository.find_blob_by_hash(blob.hash) == stored_blob

    assert (
        repository.find_blob_by_hash_in_asset(
            content_hash=blob.hash,
            asset_id=asset.id,
        )
        == stored_blob
    )

    engine.dispose()

def test_execute_update_source() -> None:
    engine = create_test_engine()
    repository = PostgreSQLRepository(engine)

    asset = Asset(
        title="Repository Update Test",
    )

    original_blob = Blob(
        asset_id=asset.id,
        hash=f"original-hash-{asset.id}",
        size=100,
        mime_type="text/plain",
    )

    updated_blob = Blob(
        asset_id=asset.id,
        hash=f"updated-hash-{asset.id}",
        size=200,
        mime_type="text/plain",
    )

    source = AssetSource(
        blob_id=original_blob.id,
        provider="integration-test",
        external_id=f"update-source-{asset.id}",
        path="/tests/original.txt",
        name="original.txt",
        version_tag="v1",
        metadata={
            "state": "original",
        },
    )

    create_decision = Decision(
        actions=[
            Action(
                type=ActionType.CREATE_ASSET,
                asset=asset,
            ),
            Action(
                type=ActionType.CREATE_BLOB,
                blob=original_blob,
            ),
            Action(
                type=ActionType.CREATE_SOURCE,
                source=source,
            ),
        ],
    )

    repository.execute(create_decision)

    create_blob_decision = Decision(
        actions=[
            Action(
                type=ActionType.CREATE_BLOB,
                blob=updated_blob,
            ),
        ],
    )

    repository.execute(create_blob_decision)

    updated_source = AssetSource(
        id=source.id,
        blob_id=updated_blob.id,
        provider=source.provider,
        external_id=source.external_id,
        path="/tests/renamed.txt",
        name="renamed.txt",
        version_tag="v2",
        metadata={
            "state": "updated",
        },
    )

    update_decision = Decision(
        actions=[
            Action(
                type=ActionType.UPDATE_SOURCE,
                source=updated_source,
            ),
        ],
    )

    repository.execute(update_decision)

    stored_source = repository.find_source(
        provider=source.provider,
        external_id=source.external_id,
    )

    assert stored_source is not None
    assert stored_source.id == source.id
    assert stored_source.blob_id == updated_blob.id
    assert stored_source.provider == source.provider
    assert stored_source.external_id == source.external_id
    assert stored_source.path == "/tests/renamed.txt"
    assert stored_source.name == "renamed.txt"
    assert stored_source.version_tag == "v2"
    assert stored_source.metadata == {
        "state": "updated",
    }

    engine.dispose()

def test_execute_deactivate_source() -> None:
    engine = create_test_engine()
    repository = PostgreSQLRepository(engine)

    asset = Asset(
        title="Repository Deactivate Test",
    )

    blob = Blob(
        asset_id=asset.id,
        hash=f"deactivate-hash-{asset.id}",
        size=128,
        mime_type="text/plain",
    )

    source = AssetSource(
        blob_id=blob.id,
        provider="integration-test",
        external_id=f"deactivate-source-{asset.id}",
        path="/tests/deactivate.txt",
        name="deactivate.txt",
        version_tag="v1",
        metadata={
            "state": "active",
        },
    )

    create_decision = Decision(
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
    )

    repository.execute(create_decision)

    stored_source = repository.find_source(
        provider=source.provider,
        external_id=source.external_id,
    )

    assert stored_source is not None
    assert stored_source.is_active is True
    assert stored_source.deleted_at is None

    stored_source.is_active = False
    stored_source.deleted_at = datetime.now(UTC)

    deactivate_decision = Decision(
        actions=[
            Action(
                type=ActionType.DEACTIVATE_SOURCE,
                source=stored_source,
            ),
        ],
    )

    repository.execute(deactivate_decision)

    deactivated_source = repository.find_source(
        provider=source.provider,
        external_id=source.external_id,
    )

    assert deactivated_source is not None
    assert deactivated_source.id == source.id
    assert deactivated_source.is_active is False
    assert deactivated_source.deleted_at is not None

    active_sources = repository.list_active_sources(
        provider=source.provider,
    )

    assert all(
        active_source.id != source.id
        for active_source in active_sources
    )

    engine.dispose()
