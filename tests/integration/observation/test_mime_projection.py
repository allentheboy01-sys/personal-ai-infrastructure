from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection

from pdi.database import create_postgres_engine
from pdi.observation import PostgreSQLObservationRepository
from pdi.repository.orm.asset import AssetORM
from pdi.repository.orm.asset_source import AssetSourceORM
from pdi.repository.orm.blob import BlobORM
from tests.integration.database_guard import require_safe_test_database_url


ROOT = Path(__file__).resolve().parents[3]


def _alembic_config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def test_enrichment_projection_uses_effective_source_mime() -> None:
    engine = create_postgres_engine(require_safe_test_database_url())
    with engine.connect() as connection:
        command.upgrade(_alembic_config(connection), "head")

    now = datetime.now(UTC)
    asset_ids = {name: uuid4() for name in ("shared", "legacy", "unknown")}
    blob_ids = {name: uuid4() for name in asset_ids}
    source_specs = (
        ("shared-python", "shared", "text/x-python"),
        ("shared-markdown", "shared", "text/markdown"),
        ("legacy", "legacy", None),
        ("unknown", "unknown", None),
    )
    source_ids = {name: uuid4() for name, _, _ in source_specs}

    try:
        with engine.begin() as connection:
            connection.execute(AssetORM.__table__.insert(), [
                {
                    "id": asset_id,
                    "resource_type": "file",
                    "title": f"mime-projection-{name}",
                    "metadata": {},
                    "created_at": now,
                    "updated_at": now,
                }
                for name, asset_id in asset_ids.items()
            ])
            connection.execute(BlobORM.__table__.insert(), [
                {
                    "id": blob_ids[name],
                    "asset_id": asset_ids[name],
                    "hash": f"mime-projection-{uuid4()}",
                    "size": 10,
                    "mime_type": {
                        "shared": "application/octet-stream",
                        "legacy": "text/plain",
                        "unknown": None,
                    }[name],
                }
                for name in asset_ids
            ])
            connection.execute(AssetSourceORM.__table__.insert(), [
                {
                    "id": source_ids[name],
                    "blob_id": blob_ids[asset_name],
                    "provider": "nextcloud",
                    "external_id": f"mime-projection-{name}",
                    "path": f"mime-projection/{name}",
                    "name": name,
                    "version_tag": "1",
                    "provider_mime_type": provider_mime,
                    "metadata": {},
                    "is_active": True,
                    "deleted_at": None,
                }
                for name, asset_name, provider_mime in source_specs
            ])

        resources = PostgreSQLObservationRepository(
            engine
        ).list_enrichment_resources(provider="nextcloud")
        projected = {
            source.source_id: source.mime_type
            for resource in resources
            for source in resource.sources
            if source.source_id in {str(value) for value in source_ids.values()}
        }

        assert projected == {
            str(source_ids["shared-python"]): "text/x-python",
            str(source_ids["shared-markdown"]): "text/markdown",
            str(source_ids["legacy"]): "text/plain",
            str(source_ids["unknown"]): None,
        }
    finally:
        with engine.begin() as connection:
            connection.execute(
                AssetSourceORM.__table__.delete().where(
                    AssetSourceORM.id.in_(source_ids.values())
                )
            )
            connection.execute(
                BlobORM.__table__.delete().where(
                    BlobORM.id.in_(blob_ids.values())
                )
            )
            connection.execute(
                AssetORM.__table__.delete().where(
                    AssetORM.id.in_(asset_ids.values())
                )
            )
        engine.dispose()
