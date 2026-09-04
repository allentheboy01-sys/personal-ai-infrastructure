from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Connection

import pdi.main as pdi_main
from pdi.adapters.immich import (
    IMMICH_INCREMENTAL_MECHANISM,
    ImmichBootstrapRequiredError,
)
from pdi.adapters.nextcloud import (
    NEXTCLOUD_INCREMENTAL_MECHANISM,
    NextcloudBootstrapRequiredError,
)
from pdi.database import create_postgres_engine
from pdi.sync_state import PostgreSQLProviderSyncStateRepository
from tests.integration.database_guard import require_safe_test_database_url


ROOT = Path(__file__).resolve().parents[2]


def _config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.mark.parametrize(
    ("provider", "mechanism", "error_type"),
    [
        (
            "nextcloud",
            NEXTCLOUD_INCREMENTAL_MECHANISM,
            NextcloudBootstrapRequiredError,
        ),
        (
            "immich",
            IMMICH_INCREMENTAL_MECHANISM,
            ImmichBootstrapRequiredError,
        ),
    ],
)
def test_main_wires_real_postgres_sync_state_before_provider_access(
    monkeypatch, provider, mechanism, error_type
) -> None:
    database_url = require_safe_test_database_url()
    engine = create_postgres_engine(database_url)
    with engine.connect() as connection:
        command.upgrade(_config(connection), "head")
    with engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM provider_sync_state")
    engine.dispose()

    settings = SimpleNamespace(
        database=SimpleNamespace(url=database_url),
        nextcloud=SimpleNamespace(
            url="https://nextcloud.invalid",
            user="test-user",
            password="test-password",
        ),
        immich=SimpleNamespace(
            url="https://immich.invalid",
            api_key="test-api-key",
        ),
        gmail=SimpleNamespace(token_file="/not-used"),
        logging=SimpleNamespace(level="INFO"),
    )
    monkeypatch.setattr(pdi_main, "load_settings", lambda selected: settings)
    monkeypatch.setattr(pdi_main, "configure_logging", lambda level: None)

    with pytest.raises(error_type):
        pdi_main.main([
            "--provider", provider, "--operation", "incremental"
        ])

    verification_engine = create_postgres_engine(database_url)
    try:
        state = PostgreSQLProviderSyncStateRepository(
            verification_engine
        ).read(provider, mechanism)
        assert state is not None
        assert state.checkpoint is None
        assert state.version == 0
        assert state.reconciliation_required is False
    finally:
        verification_engine.dispose()
