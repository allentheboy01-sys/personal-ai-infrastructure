from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, pool

from pdi.config.settings import load_database_url
from pdi.repository.orm.base import Base

import pdi.repository.orm.asset
import pdi.repository.orm.asset_source
import pdi.repository.orm.blob


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_EXPECTED_TABLES = {
    "assets",
    "blobs",
    "asset_sources",
}

if set(target_metadata.tables) != _EXPECTED_TABLES:
    raise RuntimeError(
        "Alembic ORM registration mismatch: "
        f"expected {sorted(_EXPECTED_TABLES)}, "
        f"got {sorted(target_metadata.tables)}"
    )


def _configure_context(**kwargs: object) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        transaction_per_migration=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """Generate SQL without opening a database connection."""

    _configure_context(
        url=load_database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_migrations_with_connection(
    connection: Connection,
) -> None:
    _configure_context(connection=connection)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations through an explicit PostgreSQL connection."""

    supplied_connection = config.attributes.get("connection")

    if supplied_connection is not None:
        _run_migrations_with_connection(supplied_connection)
        return

    connectable = create_engine(
        load_database_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _run_migrations_with_connection(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
