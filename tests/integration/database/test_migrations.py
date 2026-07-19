from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
import pytest
from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.pool import NullPool

from pdi.database.schema_preflight import (
    BASELINE_REVISION,
    assert_v0_1_schema,
)
from pdi.repository.orm.base import Base
from tests.integration.database_guard import (
    require_safe_test_database_url,
)

import pdi.repository.orm.asset
import pdi.repository.orm.asset_source
import pdi.repository.orm.blob


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_SQL = ROOT / "src/pdi/database/schema.sql"


def _alembic_config(connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def _run_alembic(
    engine: Engine,
    operation,
    revision: str,
) -> None:
    with engine.connect() as connection:
        operation(
            _alembic_config(connection),
            revision,
        )


def _drop_test_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("DROP TABLE IF EXISTS asset_sources")
        )
        connection.execute(
            text("DROP INDEX IF EXISTS ix_blobs_hash")
        )
        connection.execute(
            text("DROP TABLE IF EXISTS blobs")
        )
        connection.execute(
            text("DROP TABLE IF EXISTS assets")
        )
        connection.execute(
            text("DROP TABLE IF EXISTS alembic_version")
        )


def _business_snapshot(connection: Connection) -> dict:
    tables = {
        "assets": (
            "id, title, metadata, created_at, updated_at"
        ),
        "blobs": (
            "id, asset_id, hash, size, mime_type"
        ),
        "asset_sources": (
            "id, blob_id, provider, external_id, path, name, "
            "version_tag, metadata, is_active, deleted_at"
        ),
    }

    counts = {
        table_name: connection.execute(
            text(f"SELECT count(*) FROM {table_name}")
        ).scalar_one()
        for table_name in tables
    }
    rows = {
        table_name: [
            dict(row)
            for row in connection.execute(
                text(
                    f"SELECT {columns} FROM {table_name} "
                    "ORDER BY id"
                )
            ).mappings()
        ]
        for table_name, columns in tables.items()
    }

    return {
        "counts": counts,
        "rows": rows,
    }


@pytest.fixture
def migration_engine() -> Engine:
    engine = create_engine(
        require_safe_test_database_url(),
        poolclass=NullPool,
    )

    _drop_test_schema(engine)

    try:
        yield engine
    finally:
        _drop_test_schema(engine)
        _run_alembic(
            engine,
            command.upgrade,
            "head",
        )
        engine.dispose()


def test_metadata_registration() -> None:
    assert set(Base.metadata.tables) == {
        "assets",
        "blobs",
        "asset_sources",
    }


def test_empty_database_upgrade_and_schema(
    migration_engine: Engine,
) -> None:
    _run_alembic(
        migration_engine,
        command.upgrade,
        "head",
    )

    with migration_engine.connect() as connection:
        assert_v0_1_schema(
            connection,
            require_unversioned=False,
        )

        assert connection.execute(
            text(
                "SELECT version_num "
                "FROM alembic_version"
            )
        ).scalar_one() == BASELINE_REVISION


def test_upgrade_downgrade_upgrade(
    migration_engine: Engine,
) -> None:
    _run_alembic(
        migration_engine,
        command.upgrade,
        "head",
    )
    _run_alembic(
        migration_engine,
        command.downgrade,
        "base",
    )

    with migration_engine.connect() as connection:
        assert set(inspect(connection).get_table_names()) == {
            "alembic_version",
        }
        assert connection.execute(
            text("SELECT count(*) FROM alembic_version")
        ).scalar_one() == 0

    _run_alembic(
        migration_engine,
        command.upgrade,
        "head",
    )

    with migration_engine.connect() as connection:
        assert_v0_1_schema(
            connection,
            require_unversioned=False,
        )


def test_stamp_existing_v0_1_schema_preserves_data(
    migration_engine: Engine,
) -> None:
    schema_sql = SCHEMA_SQL.read_text(encoding="utf-8")

    asset_id = uuid4()
    blob_id = uuid4()
    source_id = uuid4()

    with migration_engine.connect() as connection:
        connection.exec_driver_sql(schema_sql)

    with migration_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO assets "
                "(id, title, metadata, created_at, updated_at) "
                "VALUES "
                "(:id, :title, CAST(:metadata AS jsonb), "
                "now(), now())"
            ),
            {
                "id": asset_id,
                "title": "Migration Test Asset",
                "metadata": (
                    '{"source": "migration-test", "version": 1}'
                ),
            },
        )
        connection.execute(
            text(
                "INSERT INTO blobs "
                "(id, asset_id, hash, size, mime_type) "
                "VALUES "
                "(:id, :asset_id, :hash, :size, :mime_type)"
            ),
            {
                "id": blob_id,
                "asset_id": asset_id,
                "hash": f"migration-test-{blob_id}",
                "size": 1,
                "mime_type": "text/plain",
            },
        )
        connection.execute(
            text(
                "INSERT INTO asset_sources "
                "(id, blob_id, provider, external_id, path, name, "
                "version_tag, metadata) "
                "VALUES "
                "(:id, :blob_id, :provider, :external_id, "
                ":path, :name, :version_tag, "
                "CAST(:metadata AS jsonb))"
            ),
            {
                "id": source_id,
                "blob_id": blob_id,
                "provider": "migration-test",
                "external_id": f"source-{source_id}",
                "path": "/migration/test.txt",
                "name": "test.txt",
                "version_tag": "v1",
                "metadata": (
                    '{"source": "migration-test-source", '
                    '"version": 1}'
                ),
            },
        )

    with migration_engine.connect() as connection:
        assert_v0_1_schema(connection)
        tables_before_stamp = set(
            inspect(connection).get_table_names()
        )
        snapshot_before_stamp = _business_snapshot(connection)

    assert snapshot_before_stamp["counts"] == {
        "assets": 1,
        "blobs": 1,
        "asset_sources": 1,
    }

    asset_before = snapshot_before_stamp["rows"]["assets"][0]
    blob_before = snapshot_before_stamp["rows"]["blobs"][0]
    source_before = snapshot_before_stamp["rows"][
        "asset_sources"
    ][0]

    assert asset_before["id"] == asset_id
    assert asset_before["title"] == "Migration Test Asset"
    assert asset_before["metadata"] == {
        "source": "migration-test",
        "version": 1,
    }
    assert blob_before["id"] == blob_id
    assert blob_before["asset_id"] == asset_before["id"]
    assert source_before["id"] == source_id
    assert source_before["blob_id"] == blob_before["id"]
    assert source_before["metadata"] == {
        "source": "migration-test-source",
        "version": 1,
    }

    _run_alembic(
        migration_engine,
        command.stamp,
        BASELINE_REVISION,
    )

    with migration_engine.connect() as connection:
        tables_after_stamp = set(
            inspect(connection).get_table_names()
        )
        snapshot_after_stamp = _business_snapshot(connection)

        assert connection.execute(
            text(
                "SELECT version_num "
                "FROM alembic_version"
            )
        ).scalar_one() == BASELINE_REVISION

    assert tables_after_stamp == (
        tables_before_stamp | {"alembic_version"}
    )
    assert snapshot_after_stamp == snapshot_before_stamp


def test_autogenerate_has_zero_diff(
    migration_engine: Engine,
) -> None:
    _run_alembic(
        migration_engine,
        command.upgrade,
        "head",
    )

    with migration_engine.connect() as connection:
        migration_context = MigrationContext.configure(
            connection,
            opts={
                "compare_type": True,
                "compare_server_default": True,
            },
        )

        assert compare_metadata(
            migration_context,
            Base.metadata,
        ) == []
