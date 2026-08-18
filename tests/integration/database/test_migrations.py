import logging
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
import pdi.repository.orm.observation
import pdi.repository.orm.pipeline_run


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_SQL = ROOT / "src/pdi/database/schema.sql"
QUERY_V0_2_REVISION = "1c7b2f9e4a6d"
OBSERVATION_V0_1_REVISION = "8f3a1d2c4b5e"
DATA_STATUS_V0_1_REVISION = "4d8a2c6e9f10"


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
        connection.execute(text("DROP TABLE IF EXISTS pipeline_runs"))
        connection.execute(text("DROP TABLE IF EXISTS resource_enrichments"))
        connection.execute(text("DROP TABLE IF EXISTS resource_statements"))
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
        "resource_statements",
        "resource_enrichments",
        "pipeline_runs",
    }


def test_alembic_logging_preserves_existing_loggers(
    monkeypatch,
) -> None:
    logger = logging.getLogger(
        "pdi.adapters.immich.adapter"
    )
    logger.disabled = False
    monkeypatch.setenv(
        "DATABASE__URL",
        "postgresql+psycopg://user:password@localhost/pdi_test",
    )

    command.upgrade(
        Config(str(ROOT / "alembic.ini")),
        "head",
        sql=True,
    )

    assert logger.disabled is False


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
        ).scalar_one() == DATA_STATUS_V0_1_REVISION


def test_query_v0_2_indexes_upgrade_reflection_and_downgrade(
    migration_engine: Engine,
) -> None:
    _run_alembic(
        migration_engine,
        command.upgrade,
        "head",
    )

    with migration_engine.connect() as connection:
        inspector = inspect(connection)
        asset_indexes = {
            index["name"]: index
            for index in inspector.get_indexes("assets")
        }
        source_indexes = {
            index["name"]: index
            for index in inspector.get_indexes("asset_sources")
        }
        asset_index = asset_indexes["ix_assets_created_at_id"]
        source_index = source_indexes[
            "ix_asset_sources_active_blob_id"
        ]

        assert asset_index["column_names"] == ["created_at", "id"]
        assert asset_index["unique"] is False
        assert "desc" in asset_index["column_sorting"]["created_at"]
        assert source_index["column_names"] == ["blob_id"]
        assert source_index["unique"] is False
        assert source_index["dialect_options"][
            "postgresql_where"
        ] is not None

    _run_alembic(
        migration_engine,
        command.downgrade,
        BASELINE_REVISION,
    )

    with migration_engine.connect() as connection:
        inspector = inspect(connection)
        assert "ix_assets_created_at_id" not in {
            index["name"]
            for index in inspector.get_indexes("assets")
        }
        assert "ix_asset_sources_active_blob_id" not in {
            index["name"]
            for index in inspector.get_indexes("asset_sources")
        }
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == BASELINE_REVISION


def test_observation_schema_constraints_indexes_and_downgrade(
    migration_engine: Engine,
) -> None:
    _run_alembic(migration_engine, command.upgrade, "head")

    with migration_engine.connect() as connection:
        inspector = inspect(connection)
        assert {
            "resource_statements",
            "resource_enrichments",
        }.issubset(inspector.get_table_names())
        statement_checks = {
            check["name"]
            for check in inspector.get_check_constraints(
                "resource_statements"
            )
        }
        assert statement_checks == {
            "ck_resource_statements_confidence",
            "ck_resource_statements_exactly_one_value",
            "ck_resource_statements_generator_name_nonempty",
            "ck_resource_statements_generator_type_nonempty",
            "ck_resource_statements_generator_version_nonempty",
            "ck_resource_statements_predicate_nonempty",
            "ck_resource_statements_source_kind",
            "ck_resource_statements_source_kind_nonempty",
            "ck_resource_statements_source_locator_nonempty",
            "ck_resource_statements_value_discriminator",
            "ck_resource_statements_value_type",
        }
        enrichment_checks = {
            check["name"]
            for check in inspector.get_check_constraints(
                "resource_enrichments"
            )
        }
        assert enrichment_checks == {
            "ck_resource_enrichments_fingerprint_nonempty",
            "ck_resource_enrichments_name_nonempty",
            "ck_resource_enrichments_status",
            "ck_resource_enrichments_type_nonempty",
            "ck_resource_enrichments_version_nonempty",
        }
        statement_fks = {
            foreign_key["name"]: foreign_key["options"].get(
                "ondelete"
            )
            for foreign_key in inspector.get_foreign_keys(
                "resource_statements"
            )
        }
        assert statement_fks == {
            "fk_resource_statements_resource_value_asset": "RESTRICT",
            "fk_resource_statements_subject_asset": "RESTRICT",
        }
        assert {
            foreign_key["name"]: foreign_key["options"].get(
                "ondelete"
            )
            for foreign_key in inspector.get_foreign_keys(
                "resource_enrichments"
            )
        } == {"fk_resource_enrichments_subject_asset": "RESTRICT"}
        indexes = {
            index["name"]: index
            for index in inspector.get_indexes("resource_statements")
        }
        assert {
            "ix_resource_statements_current_subject_predicate",
            "ix_resource_statements_current_generator",
            "ix_resource_statements_subject_history",
        }.issubset(indexes)
        assert indexes[
            "ix_resource_statements_current_subject_predicate"
        ]["dialect_options"]["postgresql_where"] is not None
        assert indexes[
            "ix_resource_statements_current_generator"
        ]["dialect_options"]["postgresql_where"] is not None

    _run_alembic(
        migration_engine,
        command.downgrade,
        QUERY_V0_2_REVISION,
    )
    with migration_engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        assert "resource_statements" not in tables
        assert "resource_enrichments" not in tables
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == QUERY_V0_2_REVISION


def test_data_status_schema_constraints_indexes_and_downgrade(
    migration_engine: Engine,
) -> None:
    _run_alembic(migration_engine, command.upgrade, "head")

    with migration_engine.connect() as connection:
        inspector = inspect(connection)
        assert "pipeline_runs" in inspector.get_table_names()
        assert {
            check["name"]
            for check in inspector.get_check_constraints("pipeline_runs")
        } == {
            "ck_pipeline_runs_error_code",
            "ck_pipeline_runs_key_nonempty",
            "ck_pipeline_runs_kind",
            "ck_pipeline_runs_lifecycle",
            "ck_pipeline_runs_status",
        }
        columns = {
            column["name"]: column
            for column in inspector.get_columns("pipeline_runs")
        }
        assert set(columns) == {
            "id",
            "pipeline_key",
            "kind",
            "status",
            "started_at",
            "finished_at",
            "error_code",
        }
        assert "error_message" not in columns
        indexes = {
            index["name"]: index
            for index in inspector.get_indexes("pipeline_runs")
        }
        assert set(indexes) == {
            "ix_pipeline_runs_key_started_at",
            "uq_pipeline_runs_running_key",
        }
        assert indexes["uq_pipeline_runs_running_key"]["unique"] is True
        assert indexes["uq_pipeline_runs_running_key"][
            "dialect_options"
        ]["postgresql_where"] is not None

    _run_alembic(
        migration_engine,
        command.downgrade,
        OBSERVATION_V0_1_REVISION,
    )
    with migration_engine.connect() as connection:
        assert "pipeline_runs" not in inspect(connection).get_table_names()
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == OBSERVATION_V0_1_REVISION


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
