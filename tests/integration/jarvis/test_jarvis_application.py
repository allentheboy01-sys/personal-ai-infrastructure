from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine

import jarvis.bootstrap as bootstrap
from jarvis import ToolCall
from pdi.config import Settings
from pdi.database import create_postgres_engine
from pdi.decision import Action, ActionType, Decision
from pdi.models import Asset, AssetSource, Blob
from pdi.query import (
    AssetDetail,
    AssetSummary,
    BlobView,
    SourceView,
)
from pdi.repository import PostgreSQLRepository
from tests.integration.database_guard import (
    require_safe_test_database_url,
)


ROOT = Path(__file__).resolve().parents[3]


def _alembic_config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def _upgrade_test_database_schema(engine: Engine) -> None:
    with engine.connect() as connection:
        command.upgrade(
            _alembic_config(connection),
            "head",
        )


def test_jarvis_reads_asset_chain_from_postgresql(
    monkeypatch,
) -> None:
    database_url = require_safe_test_database_url()
    engine = create_postgres_engine(database_url)

    try:
        _upgrade_test_database_schema(engine)
        repository = PostgreSQLRepository(engine)
        asset = Asset(
            title="Jarvis Integration Asset",
            metadata={"nested": {"labels": ["jarvis"]}},
        )
        blob = Blob(
            asset_id=asset.id,
            hash=f"jarvis-integration-{asset.id}",
            size=2048,
            mime_type="image/jpeg",
        )
        source = AssetSource(
            blob_id=blob.id,
            provider="jarvis-integration",
            external_id=f"source-{asset.id}",
            path="/tests/jarvis.jpg",
            name="jarvis.jpg",
            version_tag="v1",
            metadata={"favorite": True},
        )
        repository.execute(
            Decision(
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
                ]
            )
        )
        monkeypatch.setattr(
            bootstrap,
            "create_postgres_engine",
            lambda configured_url: engine,
        )
        settings = Settings(
            database={"url": database_url},
            nextcloud={
                "url": "https://unused.example",
                "user": "unused",
                "password": "unused",
            },
            _env_file=None,
        )
        application = bootstrap.create_jarvis_application(
            settings
        )

        list_result = application.execute(
            ToolCall(name="list_assets", arguments={})
        )

        assert list_result.success is True
        assert isinstance(list_result.data, tuple)
        assert all(
            isinstance(item, AssetSummary)
            for item in list_result.data
        )
        assert [
            item.id
            for item in list_result.data
        ] == sorted(
            item.id
            for item in list_result.data
        )
        assert any(
            item.id == asset.id
            for item in list_result.data
        )

        detail_result = application.execute(
            ToolCall(
                name="get_asset",
                arguments={"asset_id": asset.id},
            )
        )

        assert detail_result.success is True
        assert isinstance(detail_result.data, AssetDetail)
        detail = detail_result.data
        assert detail.id == asset.id
        assert detail.metadata["nested"]["labels"] == (
            "jarvis",
        )
        assert detail.blobs == (
            BlobView(
                id=blob.id,
                asset_id=asset.id,
                hash=blob.hash,
                size=blob.size,
                mime_type=blob.mime_type,
            ),
        )
        assert len(detail.sources) == 1
        assert isinstance(detail.sources[0], SourceView)
        assert detail.sources[0].id == source.id
        assert detail.sources[0].blob_id == blob.id
        assert detail.sources[0].metadata["favorite"] is True

        missing_result = application.execute(
            ToolCall(
                name="get_asset",
                arguments={"asset_id": Asset().id},
            )
        )

        assert missing_result.success is False
        assert missing_result.error is not None
        assert missing_result.error.code == "asset_not_found"
    finally:
        engine.dispose()
