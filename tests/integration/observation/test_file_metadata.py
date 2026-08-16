from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Engine, create_engine, func, select, text

from pdi.adapters.base import ProviderFact
from pdi.engine import SyncEngine
from pdi.identity import Matcher
from pdi.observation import (
    EnrichmentStatus,
    EnrichmentWorker,
    FileMetadataExtractor,
    PostgreSQLObservationRepository,
)
from pdi.query import format_resource_ref
from pdi.repository import PostgreSQLRepository
from pdi.repository.orm.observation import (
    ResourceEnrichmentORM,
    ResourceStatementORM,
)
from tests.integration.database_guard import require_safe_test_database_url


ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)
NEXTCLOUD_TIME = "Sun, 10 Aug 2026 00:00:00 GMT"
IMMICH_TIME = "2026-08-10T00:00:00.000Z"


def _upgrade(engine: Engine) -> None:
    with engine.connect() as connection:
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@pytest.fixture
def database():
    engine = create_engine(require_safe_test_database_url())
    _upgrade(engine)
    token = uuid4().hex
    asset_ids: set[UUID] = set()
    try:
        yield engine, token, asset_ids
    finally:
        with engine.begin() as connection:
            if asset_ids:
                ids = list(asset_ids)
                connection.execute(
                    text(
                        "DELETE FROM resource_enrichments "
                        "WHERE subject_asset_id = ANY(:ids)"
                    ),
                    {"ids": ids},
                )
                connection.execute(
                    text(
                        "DELETE FROM resource_statements "
                        "WHERE subject_asset_id = ANY(:ids) "
                        "OR resource_value_asset_id = ANY(:ids)"
                    ),
                    {"ids": ids},
                )
                connection.execute(
                    text(
                        "DELETE FROM asset_sources WHERE blob_id IN "
                        "(SELECT id FROM blobs WHERE asset_id = ANY(:ids))"
                    ),
                    {"ids": ids},
                )
                connection.execute(
                    text("DELETE FROM blobs WHERE asset_id = ANY(:ids)"),
                    {"ids": ids},
                )
                connection.execute(
                    text("DELETE FROM assets WHERE id = ANY(:ids)"),
                    {"ids": ids},
                )
        engine.dispose()


def _fact(
    token: str,
    *,
    metadata: dict,
    content_hash: str | None,
) -> ProviderFact:
    return ProviderFact(
        provider="nextcloud",
        kind="file",
        external_id=f"temporal-sync-{token}",
        name="temporal.md",
        attributes={
            "path": "temporal.md",
            "size": 8,
            "mime_type": "text/markdown",
            "version_tag": "etag-stable",
            "content_hash": content_hash,
        },
        raw=metadata,
    )


class _Adapter:
    provider_name = "nextcloud"

    def __init__(self, fact: ProviderFact) -> None:
        self.fact = fact

    def connect(self) -> None:
        return None

    def scan(self) -> tuple[ProviderFact, ...]:
        return (self.fact,)

    def open(self, fact: ProviderFact):
        pytest.fail("Temporal metadata reconciliation must not open content")


def test_sync_backfills_new_curated_metadata_with_same_version_and_blob(
    database,
) -> None:
    engine, token, asset_ids = database
    repository = PostgreSQLRepository(engine)
    original_metadata = {
        "href": "/private-provider-locator",
        "oc_id": f"temporal-sync-{token}",
        "file_id": f"file-{token}",
        "is_collection": False,
    }
    first = _fact(
        token,
        metadata=original_metadata,
        content_hash=f"temporal-hash-{token}",
    )
    SyncEngine(_Adapter(first), Matcher(), repository).sync_once()
    before = repository.find_source(
        provider="nextcloud",
        external_id=f"temporal-sync-{token}",
    )
    assert before is not None
    source_id = before.id
    blob_id = before.blob_id
    blob = repository.get_blob(blob_id)
    assert blob is not None
    asset_ids.add(UUID(blob.asset_id))

    backfilled_metadata = {
        **original_metadata,
        "getlastmodified": NEXTCLOUD_TIME,
    }
    second = _fact(
        token,
        metadata=backfilled_metadata,
        content_hash=None,
    )
    SyncEngine(_Adapter(second), Matcher(), repository).sync_once()
    after = repository.find_source(
        provider="nextcloud",
        external_id=f"temporal-sync-{token}",
    )

    assert after is not None
    assert after.id == source_id
    assert after.blob_id == blob_id
    assert after.version_tag == "etag-stable"
    assert after.metadata == backfilled_metadata

    SyncEngine(_Adapter(second), Matcher(), repository).sync_once()
    unchanged = repository.find_source(
        provider="nextcloud",
        external_id=f"temporal-sync-{token}",
    )
    assert unchanged == after
    with engine.connect() as connection:
        assert connection.execute(
            select(func.count()).select_from(ResourceStatementORM).where(
                ResourceStatementORM.subject_asset_id == UUID(blob.asset_id)
            )
        ).scalar_one() == 0


def _insert_source(
    connection,
    *,
    blob_id: UUID,
    token: str,
    provider: str,
    metadata: str,
    active: bool = True,
) -> None:
    connection.execute(
        text(
            "INSERT INTO asset_sources "
            "(id,blob_id,provider,external_id,path,name,version_tag,"
            "metadata,is_active) VALUES "
            "(:id,:blob,:provider,:external,NULL,'temporal.bin','v1',"
            "CAST(:metadata AS jsonb),:active)"
        ),
        {
            "id": uuid4(),
            "blob": blob_id,
            "provider": provider,
            "external": f"temporal-{provider}-{token}-{uuid4().hex}",
            "metadata": metadata,
            "active": active,
        },
    )


class _SingleResourceRepository:
    def __init__(
        self,
        repository: PostgreSQLObservationRepository,
        resource_ref: str,
    ) -> None:
        self._repository = repository
        self._resource_ref = resource_ref

    def list_enrichment_resources(self, *, provider):
        assert provider == ("nextcloud", "immich")
        return tuple(
            resource
            for resource in self._repository.list_enrichment_resources(
                provider=provider
            )
            if resource.resource_ref == self._resource_ref
        )

    def __getattr__(self, name):
        return getattr(self._repository, name)


def test_file_metadata_worker_union_history_idempotency_and_empty_retirement(
    database,
) -> None:
    engine, token, asset_ids = database
    asset_id, blob_id = uuid4(), uuid4()
    asset_ids.add(asset_id)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO assets "
                "(id,title,metadata,created_at,updated_at) VALUES "
                "(:id,'temporal-consensus','{}'::jsonb,:now,:now)"
            ),
            {"id": asset_id, "now": NOW},
        )
        connection.execute(
            text(
                "INSERT INTO blobs (id,asset_id,hash,size,mime_type) "
                "VALUES (:id,:asset,:hash,1,'application/octet-stream')"
            ),
            {
                "id": blob_id,
                "asset": asset_id,
                "hash": f"temporal-consensus-{token}",
            },
        )
        _insert_source(
            connection,
            blob_id=blob_id,
            token=token,
            provider="nextcloud",
            metadata=(
                '{"getlastmodified":'
                '"Sun, 10 Aug 2026 08:00:00 +0800","irrelevant":1}'
            ),
        )
        _insert_source(
            connection,
            blob_id=blob_id,
            token=token,
            provider="immich",
            metadata='{"fileModifiedAt":"2026-08-10T00:00:00.000Z"}',
        )
        _insert_source(
            connection,
            blob_id=blob_id,
            token=token,
            provider="immich",
            metadata='{"fileModifiedAt":"2030-01-01T00:00:00Z"}',
            active=False,
        )
        _insert_source(
            connection,
            blob_id=blob_id,
            token=token,
            provider="integration-test",
            metadata='{"fileModifiedAt":"2031-01-01T00:00:00Z"}',
        )

    resource_ref = format_resource_ref(asset_id)
    real_repository = PostgreSQLObservationRepository(engine)
    repository = _SingleResourceRepository(real_repository, resource_ref)
    extractor = FileMetadataExtractor()
    tick = iter(
        NOW + timedelta(seconds=index)
        for index in range(30)
    )
    worker = EnrichmentWorker(
        repository,
        extractor,
        provider=extractor.discovery_providers,
        clock=lambda: next(tick),
    )

    discovered = repository.list_enrichment_resources(
        provider=("nextcloud", "immich")
    )
    assert len(discovered) == 1
    assert {source.provider for source in discovered[0].sources} == {
        "nextcloud",
        "immich",
    }

    first = worker.run_once(batch_size=1)
    assert (
        first.discovered,
        first.processed,
        first.failed,
        first.statement_writes,
    ) == (1, 1, 0, 1)
    statements = real_repository.get_resource_statements(
        resource_ref,
        predicate="file.modified_at",
        include_history=False,
        limit=100,
    )
    assert statements is not None
    assert len(statements) == 1
    assert statements[0].value == datetime(2026, 8, 10, tzinfo=UTC)
    assert statements[0].value.utcoffset() == timedelta(0)
    assert statements[0].generator == extractor.generator
    assert statements[0].confidence is None
    assert "source_id" not in statements[0].evidence.source_locator

    second = worker.run_once(batch_size=1)
    assert (second.skipped, second.statement_writes) == (1, 0)

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE asset_sources SET metadata = "
                "jsonb_set(metadata,'{irrelevant}','2'::jsonb,true) "
                "WHERE blob_id=:blob AND provider='nextcloud'"
            ),
            {"blob": blob_id},
        )
    unrelated = worker.run_once(batch_size=1)
    assert (unrelated.skipped, unrelated.statement_writes) == (1, 0)

    with engine.begin() as connection:
        _insert_source(
            connection,
            blob_id=blob_id,
            token=token,
            provider="nextcloud",
            metadata=(
                '{"getlastmodified":'
                '"Sun, 10 Aug 2026 00:00:00 GMT"}'
            ),
        )
    source_set_changed = worker.run_once(batch_size=1)
    assert (
        source_set_changed.processed,
        source_set_changed.statement_writes,
        source_set_changed.deactivated_statements,
    ) == (1, 0, 0)

    changed_time = "2026-08-11T01:02:03.000Z"
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE asset_sources SET metadata = "
                "jsonb_set(metadata,'{getlastmodified}',"
                "'\"Mon, 11 Aug 2026 01:02:03 GMT\"'::jsonb,true) "
                "WHERE blob_id=:blob AND provider='nextcloud' AND is_active"
            ),
            {"blob": blob_id},
        )
        connection.execute(
            text(
                "UPDATE asset_sources SET metadata = "
                "jsonb_set(metadata,'{fileModifiedAt}',"
                "to_jsonb(CAST(:value AS text)),true) "
                "WHERE blob_id=:blob AND provider='immich' AND is_active"
            ),
            {"blob": blob_id, "value": changed_time},
        )
    changed = worker.run_once(batch_size=1)
    assert (
        changed.processed,
        changed.statement_writes,
        changed.deactivated_statements,
    ) == (1, 1, 1)

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE asset_sources SET metadata = "
                "jsonb_set(metadata,'{fileModifiedAt}',"
                "'\"2026-08-12T00:00:00Z\"'::jsonb,true) "
                "WHERE blob_id=:blob AND provider='immich' AND is_active"
            ),
            {"blob": blob_id},
        )
    conflict = worker.run_once(batch_size=1)
    assert (
        conflict.processed,
        conflict.failed,
        conflict.statement_writes,
        conflict.deactivated_statements,
    ) == (1, 0, 0, 1)
    assert real_repository.get_resource_statements(
        resource_ref,
        predicate="file.modified_at",
        include_history=False,
        limit=100,
    ) == ()

    state = real_repository.get_enrichment_state(
        resource_ref,
        extractor.generator,
    )
    assert state is not None
    assert state.status is EnrichmentStatus.COMPLETED
    with engine.connect() as connection:
        history = connection.execute(
            select(ResourceStatementORM.is_current).where(
                ResourceStatementORM.subject_asset_id == asset_id,
                ResourceStatementORM.predicate == "file.modified_at",
            )
        ).scalars().all()
        assert len(history) == 2
        assert all(is_current is False for is_current in history)
        enrichment_count = connection.execute(
            select(func.count()).select_from(ResourceEnrichmentORM).where(
                ResourceEnrichmentORM.subject_asset_id == asset_id,
                ResourceEnrichmentORM.extractor_name == "file_metadata",
            )
        ).scalar_one()
    assert enrichment_count == 1
