from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from pdi.person_identity import PersonRepository
from tests.integration.database_guard import require_safe_test_database_url


NOW = datetime(2026, 8, 18, 8, tzinfo=UTC)


@pytest.fixture
def people_repository():
    engine = create_engine(
        require_safe_test_database_url(), poolclass=NullPool
    )
    config = Config("alembic.ini")
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM person_sources"))
        connection.execute(text("DELETE FROM persons"))
    try:
        yield engine, PersonRepository(engine)
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM person_sources"))
            connection.execute(text("DELETE FROM persons"))
        engine.dispose()


def test_identity_idempotency_lifecycle_merge_and_split_are_conservative(
    people_repository,
) -> None:
    _, repository = people_repository
    first = repository.reconcile_inventory(
        "immich", ("person-a", "person-b"), now=NOW
    )
    source_a = repository.find_source("immich", "person-a")
    source_b = repository.find_source("immich", "person-b")
    assert first.created == 2
    assert source_a is not None and source_b is not None

    # Provider display metadata and membership are deliberately absent from
    # the identity input: the same external IDs cannot churn identity.
    second = repository.reconcile_inventory(
        "immich", ("person-a", "person-b"), now=NOW + timedelta(minutes=1)
    )
    assert second == second.__class__(2, 0, 2, 0, 0)
    assert repository.find_source("immich", "person-a").person_id == source_a.person_id

    # Merge-like disappearance only inactivates the missing source.
    merge_like = repository.reconcile_inventory(
        "immich", ("person-a",), now=NOW + timedelta(minutes=2)
    )
    assert merge_like.inactivated == 1
    inactive_b = repository.find_source("immich", "person-b")
    assert inactive_b.person_id == source_b.person_id
    assert inactive_b.inactive_at == NOW + timedelta(minutes=2)

    # Reappearance keeps identity; a split-like new ID creates a new Person.
    split_like = repository.reconcile_inventory(
        "immich",
        ("person-a", "person-b", "person-c"),
        now=NOW + timedelta(minutes=3),
    )
    assert split_like.reactivated == 1
    assert split_like.created == 1
    assert repository.find_source("immich", "person-b").person_id == source_b.person_id
    source_c = repository.find_source("immich", "person-c")
    assert source_c.person_id not in {source_a.person_id, source_b.person_id}
    with people_repository[0].connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM persons")
        ).scalar_one() == 3
        assert connection.execute(
            text("SELECT count(*) FROM person_sources")
        ).scalar_one() == 3


def test_empty_completed_inventory_inactivates_but_failure_does_not(
    people_repository,
) -> None:
    _, repository = people_repository
    source = repository.get_or_create_source(
        "immich", "person-a", now=NOW
    )
    assert repository.reconcile_inventory(
        "immich", (), now=NOW + timedelta(seconds=1)
    ).inactivated == 1
    assert repository.find_source(
        "immich", "person-a"
    ).inactive_at == NOW + timedelta(seconds=1)
    assert repository.get_person(source.person_id) is not None


def test_concurrent_duplicate_discovery_has_one_source_and_no_orphan_person(
    people_repository,
) -> None:
    _, repository = people_repository
    barrier = Barrier(2)

    def discover():
        barrier.wait()
        return repository.get_or_create_source(
            "immich", "concurrent-person", now=NOW
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        sources = list(executor.map(lambda _: discover(), range(2)))

    assert sources[0].person_id == sources[1].person_id
    with people_repository[0].connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM persons")
        ).scalar_one() == 1
        assert connection.execute(
            text("SELECT count(*) FROM person_sources")
        ).scalar_one() == 1
