import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import time
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from mcp import Client
import pytest
from sqlalchemy import Connection, func, select

from pdi.config import ImmichSettings
from pdi.database import create_postgres_engine
from pdi.decision import Action, ActionType, Decision
from pdi.models import Asset, AssetSource, Blob, ResourceType
from pdi.repository import PostgreSQLRepository
from pdi.repository.orm.asset import AssetORM
from pdi.repository.orm.asset_source import AssetSourceORM
from pdi.repository.orm.blob import BlobORM
from pdi.retrieval.providers import ImmichSemanticRetrievalAdapter
from pdi_mcp.bootstrap import create_runtime_server
from tests.integration.database_guard import require_safe_test_database_url


ROOT = Path(__file__).resolve().parents[3]


def _alembic_config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture
def retrieval_database():
    database_url = require_safe_test_database_url()
    engine = create_postgres_engine(database_url)
    with engine.connect() as connection:
        command.upgrade(_alembic_config(connection), "head")

    created_at = datetime.now(UTC)
    active_asset = AssetORM(
        id=uuid4(),
        resource_type="file",
        title="retrieval-active.jpg",
        metadata_={},
        created_at=created_at,
        updated_at=created_at,
    )
    inactive_asset = AssetORM(
        id=uuid4(),
        resource_type="file",
        title="retrieval-inactive.jpg",
        metadata_={},
        created_at=created_at,
        updated_at=created_at,
    )
    active_blob = BlobORM(
        id=uuid4(),
        asset_id=active_asset.id,
        hash=f"retrieval-{uuid4()}",
        size=100,
        mime_type="image/jpeg",
    )
    inactive_blob = BlobORM(
        id=uuid4(),
        asset_id=inactive_asset.id,
        hash=f"retrieval-{uuid4()}",
        size=200,
        mime_type="image/jpeg",
    )
    active_locator = f"active-{uuid4()}"
    inactive_locator = f"inactive-{uuid4()}"
    active_source = AssetSourceORM(
        id=uuid4(),
        blob_id=active_blob.id,
        provider="immich",
        external_id=active_locator,
        path="/retrieval/active.jpg",
        name="active.jpg",
        version_tag="1",
        metadata_={},
        is_active=True,
        deleted_at=None,
    )
    inactive_source = AssetSourceORM(
        id=uuid4(),
        blob_id=inactive_blob.id,
        provider="immich",
        external_id=inactive_locator,
        path="/retrieval/inactive.jpg",
        name="inactive.jpg",
        version_tag="1",
        metadata_={},
        is_active=False,
        deleted_at=created_at,
    )

    with engine.begin() as connection:
        connection.execute(
            AssetORM.__table__.insert(),
            [
                {
                    "id": active_asset.id,
                    "resource_type": "file",
                    "title": active_asset.title,
                    "metadata": {},
                    "created_at": created_at,
                    "updated_at": created_at,
                },
                {
                    "id": inactive_asset.id,
                    "resource_type": "file",
                    "title": inactive_asset.title,
                    "metadata": {},
                    "created_at": created_at,
                    "updated_at": created_at,
                },
            ],
        )
        connection.execute(
            BlobORM.__table__.insert(),
            [
                {
                    "id": active_blob.id,
                    "asset_id": active_asset.id,
                    "hash": active_blob.hash,
                    "size": 100,
                    "mime_type": "image/jpeg",
                },
                {
                    "id": inactive_blob.id,
                    "asset_id": inactive_asset.id,
                    "hash": inactive_blob.hash,
                    "size": 200,
                    "mime_type": "image/jpeg",
                },
            ],
        )
        connection.execute(
            AssetSourceORM.__table__.insert(),
            [
                {
                    "id": active_source.id,
                    "blob_id": active_blob.id,
                    "provider": "immich",
                    "external_id": active_locator,
                    "path": active_source.path,
                    "name": active_source.name,
                    "version_tag": "1",
                    "metadata": {},
                    "is_active": True,
                    "deleted_at": None,
                },
                {
                    "id": inactive_source.id,
                    "blob_id": inactive_blob.id,
                    "provider": "immich",
                    "external_id": inactive_locator,
                    "path": inactive_source.path,
                    "name": inactive_source.name,
                    "version_tag": "1",
                    "metadata": {},
                    "is_active": False,
                    "deleted_at": created_at,
                },
            ],
        )

    try:
        yield engine, active_locator, inactive_locator
    finally:
        with engine.begin() as connection:
            connection.execute(
                AssetSourceORM.__table__.delete().where(
                    AssetSourceORM.id.in_([
                        active_source.id,
                        inactive_source.id,
                    ])
                )
            )
            connection.execute(
                BlobORM.__table__.delete().where(
                    BlobORM.id.in_([active_blob.id, inactive_blob.id])
                )
            )
            connection.execute(
                AssetORM.__table__.delete().where(
                    AssetORM.id.in_([
                        active_asset.id,
                        inactive_asset.id,
                    ])
                )
            )
        engine.dispose()


def test_postgresql_maps_only_active_resources_without_writes(
    retrieval_database,
) -> None:
    engine, active_locator, inactive_locator = retrieval_database
    repository = PostgreSQLRepository(engine)
    with engine.connect() as connection:
        before = connection.execute(
            select(func.count()).select_from(AssetSourceORM)
        ).scalar_one()

    mappings = repository.map_active_resources(
        provider="immich",
        provider_locators=(
            active_locator,
            inactive_locator,
            "missing-locator",
        ),
    )

    assert set(mappings) == {active_locator}
    assert len(mappings[active_locator]) == 1
    summary = mappings[active_locator][0]
    assert summary.display_name == "retrieval-active.jpg"
    assert len(summary.sources) == 1
    assert summary.sources[0].is_active is True
    assert summary.sources[0].provider == "immich"
    assert summary.sources[0].mime_type == "image/jpeg"
    assert summary.display_name == "retrieval-active.jpg"

    with engine.connect() as connection:
        after = connection.execute(
            select(func.count()).select_from(AssetSourceORM)
        ).scalar_one()
    assert after == before


def test_immich_retrieval_mapping_excludes_message_resource(
    retrieval_database,
) -> None:
    engine, _, _ = retrieval_database
    repository = PostgreSQLRepository(engine)
    locator = f"typed-message-{uuid4()}"
    asset = Asset(
        resource_type=ResourceType.MESSAGE,
        title="Message",
    )
    blob = Blob(
        asset_id=asset.id,
        hash=f"typed-message-{uuid4()}",
        size=1,
        mime_type="image/jpeg",
    )
    source = AssetSource(
        blob_id=blob.id,
        provider="immich",
        external_id=locator,
    )
    repository.execute(Decision(actions=[
        Action(type=ActionType.CREATE_ASSET, asset=asset),
        Action(type=ActionType.CREATE_BLOB, blob=blob),
        Action(type=ActionType.CREATE_SOURCE, source=source),
    ]))
    try:
        assert repository.map_active_resources(
            provider="immich",
            provider_locators=(locator,),
        ) == {}
    finally:
        with engine.begin() as connection:
            connection.execute(
                AssetSourceORM.__table__.delete().where(
                    AssetSourceORM.id == UUID(source.id)
                )
            )
            connection.execute(
                BlobORM.__table__.delete().where(
                    BlobORM.id == UUID(blob.id)
                )
            )
            connection.execute(
                AssetORM.__table__.delete().where(
                    AssetORM.id == UUID(asset.id)
                )
            )


def test_live_immich_retrieval_reaches_mcp_and_isolated_postgresql() -> None:
    base_url = os.environ.get("IMMICH__URL")
    api_key = os.environ.get("IMMICH__API_KEY")
    if not base_url or not api_key:
        pytest.skip("live Immich retrieval credentials unavailable")

    database_url = require_safe_test_database_url()
    engine = create_postgres_engine(database_url)
    with engine.connect() as connection:
        command.upgrade(_alembic_config(connection), "head")

    adapter = ImmichSemanticRetrievalAdapter(base_url, api_key)
    provider_started = time.monotonic()
    provider_hits = adapter.search_resources(query="car", limit=5)
    provider_latency = time.monotonic() - provider_started
    if not provider_hits:
        engine.dispose()
        pytest.skip("live Immich semantic search returned no assets")

    now = datetime.now(UTC)
    asset_ids = [uuid4() for _ in provider_hits]
    blob_ids = [uuid4() for _ in provider_hits]
    source_ids = [uuid4() for _ in provider_hits]
    try:
        with engine.begin() as connection:
            connection.execute(AssetORM.__table__.insert(), [
                {
                    "id": asset_id,
                    "resource_type": "file",
                    "title": f"live-retrieval-{index}.jpg",
                    "metadata": {},
                    "created_at": now,
                    "updated_at": now,
                }
                for index, asset_id in enumerate(asset_ids)
            ])
            connection.execute(BlobORM.__table__.insert(), [
                {
                    "id": blob_id,
                    "asset_id": asset_id,
                    "hash": f"live-retrieval-{uuid4()}",
                    "size": 1,
                    "mime_type": "image/jpeg",
                }
                for blob_id, asset_id in zip(blob_ids, asset_ids)
            ])
            connection.execute(AssetSourceORM.__table__.insert(), [
                {
                    "id": source_id,
                    "blob_id": blob_id,
                    "provider": "immich",
                    "external_id": hit.provider_locator,
                    "path": None,
                    "name": f"live-retrieval-{index}.jpg",
                    "version_tag": "live-test",
                    "metadata": {},
                    "is_active": True,
                    "deleted_at": None,
                }
                for index, (source_id, blob_id, hit) in enumerate(
                    zip(source_ids, blob_ids, provider_hits)
                )
            ])

        server = create_runtime_server(
            database_url,
            ImmichSettings(url=base_url, api_key=api_key),
        )

        async def exercise() -> dict[str, object]:
            async with Client(server) as client:
                result = await client.call_tool(
                    "pdi_retrieve_resources",
                    {
                        "query": "car",
                        "provider": "immich",
                        "limit": 5,
                    },
                )
            return result.structured_content

        total_started = time.monotonic()
        payload = asyncio.run(exercise())
        total_latency = time.monotonic() - total_started
        assert payload["ok"] is True
        assert 1 <= len(payload["hits"]) <= 5
        assert provider_latency < 10
        assert total_latency < 10
        encoded = json.dumps(payload)
        for hit in provider_hits:
            assert hit.provider_locator not in encoded
        for private_name in (
            "provider_locator",
            "external_id",
            "asset_id",
            "blob_id",
            "source_id",
            "embedding",
            "provider_score",
            "raw",
        ):
            assert private_name not in encoded
    finally:
        with engine.begin() as connection:
            connection.execute(
                AssetSourceORM.__table__.delete().where(
                    AssetSourceORM.id.in_(source_ids)
                )
            )
            connection.execute(
                BlobORM.__table__.delete().where(
                    BlobORM.id.in_(blob_ids)
                )
            )
            connection.execute(
                AssetORM.__table__.delete().where(
                    AssetORM.id.in_(asset_ids)
                )
            )
        engine.dispose()
