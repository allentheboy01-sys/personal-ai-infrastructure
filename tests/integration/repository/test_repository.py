from pdi.database import create_postgres_engine
from pdi.config import Settings
from pdi.decision import Action, ActionType, Decision
from pdi.models import Asset, AssetSource, Blob
from pdi.repository import PostgreSQLRepository

def create_test_engine():
    settings = Settings()

    return create_postgres_engine(
        settings.database.url,
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