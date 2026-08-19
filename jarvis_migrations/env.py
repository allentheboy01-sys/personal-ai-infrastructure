import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, pool
from sqlalchemy.engine import make_url

from jarvis.state.models import Base


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
_EXPECTED_TABLES = {"jarvis_conversations", "jarvis_messages", "jarvis_turns", "jarvis_message_resource_refs"}
if set(target_metadata.tables) != _EXPECTED_TABLES:
    raise RuntimeError("Jarvis Alembic metadata registration mismatch")


def _database_url() -> str:
    raw = os.environ.get("JARVIS_DATABASE_URL", "")
    if not raw:
        raise RuntimeError("JARVIS_DATABASE_URL is required")
    _validate_url(raw)
    return raw


def _validate_url(raw: str) -> None:
    url = make_url(raw)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("Jarvis migrations require PostgreSQL")
    if (url.database or "").lower() == "pdi":
        raise RuntimeError("Jarvis migrations must not target the PDI database")


def _configure(**kwargs: object) -> None:
    context.configure(target_metadata=target_metadata, compare_type=True, compare_server_default=True, transaction_per_migration=True, version_table="jarvis_alembic_version", **kwargs)


def run_migrations_offline() -> None:
    _configure(url=_database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied = config.attributes.get("connection")
    if supplied is not None:
        _validate_url(supplied.engine.url.render_as_string(hide_password=False))
        _run(supplied)
        return
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        _run(connection)


def _run(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
