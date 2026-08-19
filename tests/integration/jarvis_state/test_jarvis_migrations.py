import os
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from jarvis.state import Base


ROOT = Path(__file__).resolve().parents[3]
EXPECTED = {"jarvis_alembic_version", "jarvis_conversations", "jarvis_messages", "jarvis_turns", "jarvis_message_resource_refs"}


def _isolated_url() -> str:
    raw = os.environ.get("JARVIS_TEST_DATABASE_URL", "")
    if not raw:
        pytest.skip("JARVIS_TEST_DATABASE_URL is required")
    url = make_url(raw)
    if url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_test"):
        pytest.fail("JARVIS_TEST_DATABASE_URL must be an isolated PostgreSQL database ending in _test")
    identity = ((url.host or "").lower(), url.port or 5432, url.database)
    protected = [os.environ.get(name) for name in ("PDI_TEST_DATABASE_URL", "DATABASE__URL", "JARVIS_DATABASE_URL")]
    protected_identities = {
        ((candidate.host or "").lower(), candidate.port or 5432, candidate.database)
        for value in protected if value
        for candidate in [make_url(value)]
    }
    if identity in protected_identities or (url.database or "").lower() in {"pdi", "jarvis"}:
        pytest.fail("Jarvis integration tests refuse production or shared PDI databases")
    return raw


def test_independent_jarvis_migration_from_empty_postgresql() -> None:
    engine = create_engine(_isolated_url())
    config = Config(str(ROOT / "jarvis-alembic.ini"))
    with engine.begin() as connection:
        assert inspect(connection).get_table_names() == []
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert set(inspect(connection).get_table_names()) == EXPECTED
        assert connection.scalar(text("SELECT count(*) FROM jarvis_alembic_version")) == 1
        assert not any(name.startswith("assets") or name == "alembic_version" for name in inspect(connection).get_table_names())
        context = MigrationContext.configure(connection, opts={"version_table": "jarvis_alembic_version"})
        assert compare_metadata(context, Base.metadata) == []
        command.downgrade(config, "base")
        assert set(inspect(connection).get_table_names()) == {"jarvis_alembic_version"}
    engine.dispose()
