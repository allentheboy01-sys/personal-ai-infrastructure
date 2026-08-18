import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from mcp import Client
import pytest
from sqlalchemy import create_engine, text

from pdi.observation import (
    EnrichmentStatus,
    EnrichmentWorker,
    ImmichGeoExtractor,
    PostgreSQLObservationRepository,
)
from pdi.query import format_resource_ref
from pdi_mcp.bootstrap import create_runtime_server
from tests.integration.database_guard import require_safe_test_database_url


ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 8, 18, tzinfo=UTC)


def _upgrade(engine) -> None:
    with engine.connect() as connection:
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@pytest.fixture
def database():
    database_url = require_safe_test_database_url()
    engine = create_engine(database_url)
    _upgrade(engine)
    asset_ids: set[UUID] = set()
    try:
        yield database_url, engine, asset_ids
    finally:
        if asset_ids:
            ids = list(asset_ids)
            with engine.begin() as connection:
                connection.execute(text(
                    "DELETE FROM resource_enrichments "
                    "WHERE subject_asset_id = ANY(:ids)"
                ), {"ids": ids})
                connection.execute(text(
                    "DELETE FROM resource_statements "
                    "WHERE subject_asset_id = ANY(:ids) "
                    "OR resource_value_asset_id = ANY(:ids)"
                ), {"ids": ids})
                connection.execute(text(
                    "DELETE FROM asset_sources WHERE blob_id IN "
                    "(SELECT id FROM blobs WHERE asset_id = ANY(:ids))"
                ), {"ids": ids})
                connection.execute(text(
                    "DELETE FROM blobs WHERE asset_id = ANY(:ids)"
                ), {"ids": ids})
                connection.execute(text(
                    "DELETE FROM assets WHERE id = ANY(:ids)"
                ), {"ids": ids})
        engine.dispose()


def _insert_resource(
    engine,
    asset_ids: set[UUID],
    token: str,
    exif: dict,
) -> tuple[str, UUID, UUID]:
    asset_id, blob_id, source_id = uuid4(), uuid4(), uuid4()
    asset_ids.add(asset_id)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO assets "
            "(id,title,metadata,created_at,updated_at) VALUES "
            "(:id,'geo-fixture','{}'::jsonb,:now,:now)"
        ), {"id": asset_id, "now": NOW})
        connection.execute(text(
            "INSERT INTO blobs (id,asset_id,hash,size,mime_type) "
            "VALUES (:id,:asset,:hash,1,'image/jpeg')"
        ), {
            "id": blob_id,
            "asset": asset_id,
            "hash": f"geo-{token}-{asset_id}",
        })
        connection.execute(text(
            "INSERT INTO asset_sources "
            "(id,blob_id,provider,external_id,path,name,version_tag,"
            "metadata,is_active) VALUES "
            "(:id,:blob,'immich',:external,NULL,'geo.jpg','v1',"
            "CAST(:metadata AS jsonb),true)"
        ), {
            "id": source_id,
            "blob": blob_id,
            "external": f"geo-{token}-{source_id}",
            "metadata": json.dumps({"exif": exif}),
        })
    return format_resource_ref(asset_id), blob_id, source_id


class _SingleResourceRepository:
    def __init__(
        self,
        repository: PostgreSQLObservationRepository,
        resource_ref: str,
    ) -> None:
        self._repository = repository
        self._resource_ref = resource_ref

    def list_enrichment_resources(self, *, provider):
        assert provider == "immich"
        return tuple(
            resource
            for resource in self._repository.list_enrichment_resources(
                provider=provider
            )
            if resource.resource_ref == self._resource_ref
        )

    def __getattr__(self, name):
        return getattr(self._repository, name)


def _worker(repository) -> EnrichmentWorker:
    return EnrichmentWorker(
        repository,
        ImmichGeoExtractor(),
        provider="immich",
    )


def _current_values(repository, resource_ref: str) -> dict[str, object]:
    statements = repository.get_resource_statements(
        resource_ref,
        predicate=None,
        include_history=False,
        limit=100,
    )
    assert statements is not None
    return {
        statement.predicate: statement.value
        for statement in statements
        if statement.generator.generator_name == "immich_geo"
    }


def _set_exif(engine, source_id: UUID, exif: dict) -> None:
    with engine.begin() as connection:
        connection.execute(text(
            "UPDATE asset_sources SET metadata=CAST(:metadata AS jsonb) "
            "WHERE id=:id"
        ), {
            "id": source_id,
            "metadata": json.dumps({"exif": exif}),
        })


def test_geo_lifecycle_mcp_idempotency_history_and_retirement(
    database,
) -> None:
    database_url, engine, asset_ids = database
    token = uuid4().hex
    resource_ref, _, source_id = _insert_resource(
        engine,
        asset_ids,
        token,
        {
            "latitude": 52.2,
            "longitude": 0.1,
            "country": "United Kingdom",
            "state": "England",
            "city": "Cambridge",
            "make": "Ignored Camera",
        },
    )
    real = PostgreSQLObservationRepository(engine)
    repository = _SingleResourceRepository(real, resource_ref)
    worker = _worker(repository)

    first = worker.run_once(batch_size=1)
    assert (
        first.discovered,
        first.processed,
        first.skipped,
        first.failed,
        first.statement_writes,
        first.deactivated_statements,
    ) == (1, 1, 0, 0, 3, 0)
    assert _current_values(real, resource_ref) == {
        "geo.country": "United Kingdom",
        "geo.admin1": "England",
        "geo.locality": "Cambridge",
    }

    async def exercise_mcp() -> None:
        async with Client(
            create_runtime_server(database_url)
        ) as client:
            tools = (await client.list_tools()).tools
            result = await client.call_tool(
                "pdi_get_resource_observations",
                {"resource_ref": resource_ref},
            )
        assert len(tools) == 8
        geo = {
            item["predicate"]: item
            for item in result.structured_content["observations"]
            if item["generator_name"] == "immich_geo"
        }
        assert {name: item["value"] for name, item in geo.items()} == {
            "geo.country": "United Kingdom",
            "geo.admin1": "England",
            "geo.locality": "Cambridge",
        }
        assert all(
            item["generator_type"] == "deterministic_extractor"
            and item["generator_version"] == "1"
            and item["source_kind"] == "provider_metadata"
            and item["confidence"] is None
            for item in geo.values()
        )
        payload = json.dumps(result.structured_content)
        for forbidden in (
            "latitude",
            "longitude",
            "source_id",
            "external_id",
            "provider_locator",
            "raw",
        ):
            assert forbidden not in payload

    asyncio.run(exercise_mcp())

    second = worker.run_once(batch_size=1)
    assert (second.processed, second.skipped, second.statement_writes) == (
        0,
        1,
        0,
    )

    _set_exif(engine, source_id, {
        "latitude": 52.2,
        "longitude": 0.1,
        "country": "United Kingdom",
        "state": "England",
        "city": "Cambridge",
        "make": "Different Ignored Camera",
        "favorite": True,
    })
    unrelated = worker.run_once(batch_size=1)
    assert (unrelated.processed, unrelated.skipped) == (0, 1)

    before_state = real.get_enrichment_state(
        resource_ref,
        ImmichGeoExtractor.generator,
    )
    assert before_state is not None
    _set_exif(engine, source_id, {
        "latitude": 52.200001,
        "longitude": 0.1,
        "country": "United Kingdom",
        "state": "England",
        "city": "Cambridge",
    })
    moved_same_labels = worker.run_once(batch_size=1)
    assert (
        moved_same_labels.processed,
        moved_same_labels.statement_writes,
        moved_same_labels.deactivated_statements,
    ) == (1, 0, 0)
    after_state = real.get_enrichment_state(
        resource_ref,
        ImmichGeoExtractor.generator,
    )
    assert after_state is not None
    assert after_state.input_fingerprint != before_state.input_fingerprint

    _set_exif(engine, source_id, {
        "latitude": 52.200001,
        "longitude": 0.1,
        "country": "United Kingdom",
        "state": "England",
        "city": "Other Locality",
    })
    changed_label = worker.run_once(batch_size=1)
    assert (
        changed_label.processed,
        changed_label.statement_writes,
        changed_label.deactivated_statements,
    ) == (1, 3, 3)
    assert _current_values(real, resource_ref)["geo.locality"] == (
        "Other Locality"
    )

    _set_exif(engine, source_id, {
        "latitude": 52.200001,
        "longitude": 0.1,
        "country": "United Kingdom",
        "state": None,
        "city": None,
    })
    partial = worker.run_once(batch_size=1)
    assert (
        partial.processed,
        partial.statement_writes,
        partial.deactivated_statements,
    ) == (1, 1, 3)
    assert _current_values(real, resource_ref) == {
        "geo.country": "United Kingdom",
    }

    _set_exif(engine, source_id, {
        "latitude": None,
        "longitude": None,
        "country": "United Kingdom",
        "state": "England",
        "city": "Cambridge",
    })
    gps_removed = worker.run_once(batch_size=1)
    assert (
        gps_removed.processed,
        gps_removed.statement_writes,
        gps_removed.deactivated_statements,
    ) == (1, 0, 1)
    assert _current_values(real, resource_ref) == {}

    history = real.get_resource_statements(
        resource_ref,
        predicate=None,
        include_history=True,
        limit=100,
    )
    assert history is not None
    geo_history = tuple(
        statement
        for statement in history
        if statement.generator.generator_name == "immich_geo"
    )
    assert geo_history
    assert all(statement.is_current is False for statement in geo_history)

    with engine.begin() as connection:
        connection.execute(text(
            "UPDATE asset_sources SET is_active=false WHERE id=:id"
        ), {"id": source_id})
    inactive = worker.run_once(batch_size=1)
    assert inactive.discovered == 0


def test_multiple_active_immich_sources_fail_without_partial_publish(
    database,
) -> None:
    _, engine, asset_ids = database
    token = uuid4().hex
    resource_ref, blob_id, _ = _insert_resource(
        engine,
        asset_ids,
        token,
        {
            "latitude": 1.0,
            "longitude": 2.0,
            "country": "Country",
        },
    )
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO asset_sources "
            "(id,blob_id,provider,external_id,path,name,version_tag,"
            "metadata,is_active) VALUES "
            "(:id,:blob,'immich',:external,NULL,'geo-2.jpg','v1',"
            "CAST(:metadata AS jsonb),true)"
        ), {
            "id": uuid4(),
            "blob": blob_id,
            "external": f"geo-second-{token}",
            "metadata": json.dumps({"exif": {
                "latitude": 1.0,
                "longitude": 2.0,
                "country": "Country",
            }}),
        })
    real = PostgreSQLObservationRepository(engine)
    repository = _SingleResourceRepository(real, resource_ref)

    result = _worker(repository).run_once(batch_size=1)

    assert (
        result.discovered,
        result.processed,
        result.failed,
        result.statement_writes,
    ) == (1, 0, 1, 0)
    assert _current_values(real, resource_ref) == {}
    state = real.get_enrichment_state(
        resource_ref,
        ImmichGeoExtractor.generator,
    )
    assert state is not None
    assert state.status is EnrichmentStatus.FAILED
    assert state.error_code == "ambiguous_active_immich_sources"
