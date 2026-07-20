import os
from collections.abc import Iterable

import pytest
from sqlalchemy import Engine, text

from pdi.adapters.base import ProviderFact
from pdi.adapters.immich import ImmichAdapter
from pdi.database import create_postgres_engine
from pdi.engine import SyncEngine
from pdi.identity import Matcher
from pdi.repository import PostgreSQLRepository
from tests.integration.database_guard import (
    require_safe_test_database_url,
)


def _require_immich_configuration() -> tuple[str, str]:
    url = os.environ.get("IMMICH__URL")
    api_key = os.environ.get("IMMICH__API_KEY")

    if not url or not api_key:
        pytest.skip(
            "IMMICH__URL and IMMICH__API_KEY are required for "
            "the Immich integration test"
        )

    return url, api_key


def _database_counts(
    engine: Engine,
) -> tuple[int, int]:
    with engine.connect() as connection:
        source_count = connection.execute(
            text(
                "SELECT count(*) FROM asset_sources "
                "WHERE provider = :provider"
            ),
            {
                "provider": "immich",
            },
        ).scalar_one()
        blob_count = connection.execute(
            text("SELECT count(*) FROM blobs")
        ).scalar_one()

    return source_count, blob_count


def test_immich_sync_is_persisted_and_idempotent(
    monkeypatch,
) -> None:
    immich_url, api_key = _require_immich_configuration()
    database_url = require_safe_test_database_url()
    engine = create_postgres_engine(database_url)

    try:
        adapter = ImmichAdapter(
            base_url=immich_url,
            api_key=api_key,
        )
        repository = PostgreSQLRepository(engine)
        matcher = Matcher()

        adapter.connect()
        facts = list(adapter.scan())

        if not facts:
            pytest.skip(
                "Immich integration server returned no file assets"
            )

        selected_fact = facts[0]
        external_id = selected_fact.external_id

        assert isinstance(external_id, str)
        assert external_id

        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM asset_sources "
                    "WHERE provider = :provider"
                ),
                {
                    "provider": adapter.provider_name,
                },
            )

        original_scan = adapter.scan

        def scan_selected_asset() -> Iterable[ProviderFact]:
            return (
                fact
                for fact in original_scan()
                if fact.external_id == external_id
            )

        monkeypatch.setattr(
            adapter,
            "scan",
            scan_selected_asset,
        )

        sync_engine = SyncEngine(
            adapter=adapter,
            matcher=matcher,
            repository=repository,
        )

        sync_engine.sync_once()

        first_source = repository.find_source(
            provider=adapter.provider_name,
            external_id=external_id,
        )

        assert first_source is not None
        assert first_source.blob_id is not None

        first_blob = repository.get_blob(
            first_source.blob_id,
        )

        assert first_blob is not None
        assert first_blob.asset_id is not None
        assert isinstance(first_blob.hash, str)
        assert len(first_blob.hash) == 64
        assert all(
            character in "0123456789abcdef"
            for character in first_blob.hash
        )

        first_asset = repository.get_asset(
            first_blob.asset_id,
        )

        assert first_asset is not None

        first_source_id = first_source.id
        first_blob_id = first_blob.id
        counts_after_first_sync = _database_counts(engine)

        sync_engine.sync_once()

        second_source = repository.find_source(
            provider=adapter.provider_name,
            external_id=external_id,
        )

        assert second_source is not None
        assert second_source.id == first_source_id
        assert second_source.blob_id == first_blob_id
        assert _database_counts(engine) == counts_after_first_sync
    finally:
        engine.dispose()
