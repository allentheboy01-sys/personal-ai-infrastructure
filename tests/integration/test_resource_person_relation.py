from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from pdi.resource_person_relation import ResourcePersonRelationRepository
from tests.integration.database_guard import require_safe_test_database_url


NOW = datetime(2026, 8, 18, 8, tzinfo=UTC)


@pytest.fixture
def relation_database():
    engine = create_engine(require_safe_test_database_url(), poolclass=NullPool)
    config = Config("alembic.ini")
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM resource_person_relations"))
        connection.execute(text("DELETE FROM person_sources"))
        connection.execute(text("DELETE FROM persons"))
        connection.execute(text("DELETE FROM asset_sources"))
        connection.execute(text("DELETE FROM blobs"))
        connection.execute(text("DELETE FROM assets"))

        data = {}
        for label, active in (("a", True), ("b", True), ("inactive", False)):
            asset_id, blob_id, source_id = uuid4(), uuid4(), uuid4()
            data[f"asset_{label}"] = asset_id
            connection.execute(text("INSERT INTO assets (id,resource_type,title,metadata,created_at,updated_at) VALUES (:id,'file',:title,'{}',:now,:now)"), {"id": asset_id, "title": label, "now": NOW})
            connection.execute(text("INSERT INTO blobs (id,asset_id,hash,size,mime_type) VALUES (:id,:asset,:hash,1,'image/jpeg')"), {"id": blob_id, "asset": asset_id, "hash": str(blob_id)})
            connection.execute(text("INSERT INTO asset_sources (id,blob_id,provider,external_id,path,name,version_tag,metadata,is_active,deleted_at) VALUES (:id,:blob,'immich',:external,NULL,NULL,NULL,'{}',:active,:deleted)"), {"id": source_id, "blob": blob_id, "external": f"asset-{label}", "active": active, "deleted": None if active else NOW})
        for label, active in (("a", True), ("b", True), ("inactive", False)):
            person_id = uuid4()
            data[f"person_{label}"] = person_id
            connection.execute(text("INSERT INTO persons (id,created_at) VALUES (:id,:now)"), {"id": person_id, "now": NOW})
            connection.execute(text("INSERT INTO person_sources (provider,external_id,person_id,inactive_at) VALUES ('immich',:external,:person,:inactive)"), {"external": f"person-{label}", "person": person_id, "inactive": None if active else NOW})
    try:
        yield engine, ResourcePersonRelationRepository(engine), data
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM resource_person_relations"))
            connection.execute(text("DELETE FROM person_sources"))
            connection.execute(text("DELETE FROM persons"))
            connection.execute(text("DELETE FROM asset_sources"))
            connection.execute(text("DELETE FROM blobs"))
            connection.execute(text("DELETE FROM assets"))
        engine.dispose()


def rows(engine):
    with engine.connect() as connection:
        return connection.execute(text("SELECT resource_id,person_id,provider,inactive_at FROM resource_person_relations ORDER BY provider,resource_id,person_id")).all()


def test_reconcile_create_deduplicate_idempotency_reactivate_and_missing(relation_database):
    engine, repository, _ = relation_database
    observed = (("asset-a", "person-a"), ("asset-a", "person-a"), ("asset-b", "person-b"))
    first = repository.reconcile_provider_relations("immich", observed, now=NOW)
    assert (first.created, first.observed, first.skipped_unmapped) == (2, 2, 0)
    assert len(rows(engine)) == 2
    second = repository.reconcile_provider_relations("immich", observed, now=NOW + timedelta(minutes=1))
    assert (second.created, second.unchanged, second.inactivated) == (0, 2, 0)
    missing = repository.reconcile_provider_relations("immich", (("asset-a", "person-a"),), now=NOW + timedelta(minutes=2))
    assert missing.inactivated == 1
    reactivated = repository.reconcile_provider_relations("immich", observed, now=NOW + timedelta(minutes=3))
    assert reactivated.reactivated == 1


def test_inactive_sources_and_unmapped_fixture_are_skipped_and_inactivate(relation_database):
    engine, repository, _ = relation_database
    repository.reconcile_provider_relations("immich", (("asset-a", "person-a"),), now=NOW)
    inactive = repository.reconcile_provider_relations("immich", (("asset-inactive", "person-a"), ("asset-a", "person-inactive")), now=NOW + timedelta(minutes=2))
    assert inactive.skipped_unmapped == 2
    assert inactive.inactivated == 1
    assert rows(engine)[0].inactive_at == NOW + timedelta(minutes=2)


def test_audited_production_shape_skips_114_without_identity_changes(
    relation_database,
):
    engine, repository, _ = relation_database
    asset_ids = ["asset-a", "asset-b"]
    person_ids = ["person-a", "person-b"]
    with engine.begin() as connection:
        for index in range(24):
            asset_id, blob_id, source_id = uuid4(), uuid4(), uuid4()
            external = f"fixture-asset-{index}"
            asset_ids.append(external)
            connection.execute(text("INSERT INTO assets (id,resource_type,title,metadata,created_at,updated_at) VALUES (:id,'file',:title,'{}',:now,:now)"), {"id": asset_id, "title": external, "now": NOW})
            connection.execute(text("INSERT INTO blobs (id,asset_id,hash,size,mime_type) VALUES (:id,:asset,:hash,1,'image/jpeg')"), {"id": blob_id, "asset": asset_id, "hash": str(blob_id)})
            connection.execute(text("INSERT INTO asset_sources (id,blob_id,provider,external_id,path,name,version_tag,metadata,is_active,deleted_at) VALUES (:id,:blob,'immich',:external,NULL,NULL,NULL,'{}',TRUE,NULL)"), {"id": source_id, "blob": blob_id, "external": external})
        for index in range(415):
            person_id = uuid4()
            external = f"fixture-person-{index}"
            person_ids.append(external)
            connection.execute(text("INSERT INTO persons (id,created_at) VALUES (:id,:now)"), {"id": person_id, "now": NOW})
            connection.execute(text("INSERT INTO person_sources (provider,external_id,person_id,inactive_at) VALUES ('immich',:external,:person,NULL)"), {"external": external, "person": person_id})

    mappable = tuple(
        (asset, person)
        for asset in asset_ids
        for person in person_ids
    )[:10460]
    outside_people = tuple(f"outside-{index}" for index in range(84))
    unmappable = tuple(
        (asset_ids[index % len(asset_ids)], outside_people[index % 84])
        for index in range(114)
    )
    result = repository.reconcile_provider_relations(
        "immich", mappable + unmappable, now=NOW
    )
    assert len(set(person_ids) | set(outside_people)) == 501
    assert result.observed == 10574
    assert result.created == 10460
    assert result.skipped_unmapped == 114
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM persons")).scalar_one() == 418
        assert connection.execute(text("SELECT count(*) FROM person_sources WHERE inactive_at IS NULL")).scalar_one() == 417
        assert connection.execute(text("SELECT count(*) FROM resource_person_relations")).scalar_one() == 10460


def test_provider_isolation_and_concurrent_same_pair(relation_database):
    engine, repository, data = relation_database
    repository.reconcile_provider_relations("immich", (("asset-a", "person-a"),), now=NOW)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO resource_person_relations (resource_id,person_id,provider,inactive_at) VALUES (:resource,:person,'other',NULL)"), {"resource": data["asset_a"], "person": data["person_a"]})
    repository.reconcile_provider_relations("immich", (), now=NOW + timedelta(minutes=1))
    assert {row.provider: row.inactive_at for row in rows(engine)} == {"immich": NOW + timedelta(minutes=1), "other": None}

    repository.reconcile_provider_relations("immich", (), now=NOW + timedelta(minutes=2))
    barrier = Barrier(2)
    def run():
        barrier.wait()
        return repository.reconcile_provider_relations("immich", (("asset-b", "person-b"),), now=NOW + timedelta(minutes=3))
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: run(), range(2)))
    assert sum(row.provider == "immich" and row.inactive_at is None for row in rows(engine)) == 1


def test_fk_integrity_and_no_orphan_relation(relation_database):
    engine, _, data = relation_database
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO resource_person_relations (resource_id,person_id,provider,inactive_at) VALUES (:resource,:person,'immich',NULL)"), {"resource": uuid4(), "person": data["person_a"]})
