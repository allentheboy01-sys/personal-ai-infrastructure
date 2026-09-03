from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Connection

from pdi.adapters.base import ProviderFact
from pdi.adapters.immich import (
    IMMICH_INCREMENTAL_MECHANISM,
    ImmichBootstrapRequiredError,
    ImmichIncrementalSync,
    ImmichPaginationDriftError,
)
from pdi.database import create_postgres_engine
from pdi.engine import InvalidCheckpointError, SyncEngine
from pdi.identity import Matcher
from pdi.repository import PostgreSQLRepository
from pdi.sync_state import PostgreSQLProviderSyncStateRepository
from tests.integration.database_guard import require_safe_test_database_url


ROOT = Path(__file__).resolve().parents[2]
T0 = "2026-09-03T01:00:00.000000Z"
T1 = datetime(2026, 9, 3, 1, 10, tzinfo=UTC)


def _alembic_config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture
def context():
    database_engine = create_postgres_engine(require_safe_test_database_url())
    with database_engine.connect() as connection:
        command.upgrade(_alembic_config(connection), "head")
    with database_engine.begin() as connection:
        connection.exec_driver_sql("TRUNCATE TABLE assets CASCADE")
        connection.exec_driver_sql("DELETE FROM provider_sync_state")
    adapter = _ControlledImmichAdapter("immich")
    repository = PostgreSQLRepository(database_engine)
    state_repository = PostgreSQLProviderSyncStateRepository(database_engine)
    sync_engine = SyncEngine(
        adapter, Matcher(), repository, state_repository
    )
    try:
        yield adapter, repository, state_repository, sync_engine
    finally:
        database_engine.dispose()


def _fact(provider: str, external_id: str, *, trashed: bool = False):
    body = external_id.encode()
    return ProviderFact(
        provider=provider,
        kind="file",
        external_id=external_id,
        name=f"{external_id}.jpg",
        attributes={
            "path": f"/library/{external_id}.jpg",
            "size": len(body),
            "mime_type": "image/jpeg",
            "version_tag": "v1",
            "content_hash": None,
        },
        raw={"trashed": trashed},
    )


class _ControlledImmichAdapter:
    def __init__(self, provider: str) -> None:
        self.provider_name = provider
        self.full_facts: Iterable[ProviderFact] = ()
        self.incremental_facts: Iterable[ProviderFact] = ()
        self.windows: list[tuple[str, str]] = []

    def connect(self) -> None:
        return None

    def scan(self) -> Iterable[ProviderFact]:
        return self.full_facts

    def scan_updated_window(self, *, updated_after, updated_before):
        self.windows.append((updated_after, updated_before))
        return self.incremental_facts

    def open(self, fact: ProviderFact):
        assert fact.external_id is not None
        yield fact.external_id.encode()


def _initialize_checkpoint(state_repository, provider: str) -> None:
    state = state_repository.get_or_create(
        provider, IMMICH_INCREMENTAL_MECHANISM
    )
    advanced = state_repository.compare_and_swap_checkpoint(
        provider,
        IMMICH_INCREMENTAL_MECHANISM,
        expected_version=state.version,
        checkpoint=T0,
    )
    assert advanced is not None


def test_postgres_incremental_scope_absence_does_not_deactivate(context):
    adapter, repository, state_repository, engine = context
    adapter.full_facts = tuple(
        _fact(adapter.provider_name, external_id)
        for external_id in ("a", "b", "c")
    )
    engine.sync_once()
    _initialize_checkpoint(state_repository, adapter.provider_name)
    adapter.incremental_facts = (
        _fact(adapter.provider_name, "a"),
        _fact(adapter.provider_name, "d"),
    )

    state = ImmichIncrementalSync(
        adapter, engine, state_repository, clock=lambda: T1
    ).run_incremental()

    assert state.checkpoint == "2026-09-03T01:10:00.000000Z"
    sources = {
        source.external_id: source
        for source in repository.list_active_sources(adapter.provider_name)
    }
    assert set(sources) == {"a", "b", "c", "d"}
    assert adapter.windows == [(
        "2026-09-03T00:55:00.000000Z",
        "2026-09-03T01:10:00.000000Z",
    )]


def test_postgres_partial_page_failure_replays_without_duplicates(context):
    adapter, repository, state_repository, engine = context
    _initialize_checkpoint(state_repository, adapter.provider_name)

    def failed_page_two():
        yield _fact(adapter.provider_name, "a")
        yield _fact(adapter.provider_name, "d")
        raise ImmichPaginationDriftError("page 2 total changed")

    adapter.incremental_facts = failed_page_two()
    service = ImmichIncrementalSync(
        adapter, engine, state_repository, clock=lambda: T1
    )
    with pytest.raises(ImmichPaginationDriftError, match="total changed"):
        service.run_incremental()

    unchanged = state_repository.read(
        adapter.provider_name, IMMICH_INCREMENTAL_MECHANISM
    )
    assert unchanged is not None
    assert unchanged.checkpoint == T0
    assert unchanged.reconciliation_required is False
    first_ids = {
        external_id: repository.find_source(adapter.provider_name, external_id).id
        for external_id in ("a", "d")
    }

    adapter.incremental_facts = tuple(
        _fact(adapter.provider_name, external_id)
        for external_id in ("a", "d", "e")
    )
    advanced = service.run_incremental()

    assert advanced.checkpoint == "2026-09-03T01:10:00.000000Z"
    assert {
        source.external_id
        for source in repository.list_active_sources(adapter.provider_name)
    } == {"a", "d", "e"}
    assert repository.find_source(adapter.provider_name, "a").id == first_ids["a"]
    assert repository.find_source(adapter.provider_name, "d").id == first_ids["d"]


def test_postgres_null_incremental_requires_bootstrap_without_state_change(context):
    adapter, repository, state_repository, engine = context
    service = ImmichIncrementalSync(
        adapter, engine, state_repository, clock=lambda: T1
    )

    with pytest.raises(ImmichBootstrapRequiredError):
        service.run_incremental()

    state = state_repository.read(
        adapter.provider_name, IMMICH_INCREMENTAL_MECHANISM
    )
    assert state is not None
    assert state.checkpoint is None
    assert state.version == 0
    assert state.reconciliation_required is False
    assert repository.list_active_sources(adapter.provider_name) == []


def test_postgres_bootstrap_and_recovery_commit_only_after_full_success(context):
    adapter, repository, state_repository, engine = context
    adapter.full_facts = (_fact(adapter.provider_name, "a"),)
    service = ImmichIncrementalSync(
        adapter, engine, state_repository, clock=lambda: T1
    )

    bootstrapped = service.bootstrap()
    assert bootstrapped.checkpoint == "2026-09-03T01:10:00.000000Z"
    assert repository.find_source(adapter.provider_name, "a") is not None

    marked = state_repository.mark_reconciliation_required(
        adapter.provider_name,
        IMMICH_INCREMENTAL_MECHANISM,
        expected_version=bootstrapped.version,
    )
    assert marked is not None
    recovered = service.recover()
    assert recovered.reconciliation_required is False
    assert recovered.checkpoint == "2026-09-03T01:10:00.000000Z"

    marked_again = state_repository.mark_reconciliation_required(
        adapter.provider_name,
        IMMICH_INCREMENTAL_MECHANISM,
        expected_version=recovered.version,
    )
    assert marked_again is not None

    def fail_full():
        raise ImmichPaginationDriftError("recovery membership drift")
        yield  # pragma: no cover

    adapter.full_facts = fail_full()
    with pytest.raises(ImmichPaginationDriftError, match="membership drift"):
        service.recover()
    unchanged = state_repository.read(
        adapter.provider_name, IMMICH_INCREMENTAL_MECHANISM
    )
    assert unchanged == marked_again


def test_postgres_failed_bootstrap_leaves_checkpoint_uninitialized(context):
    adapter, _, state_repository, engine = context

    def fail_full():
        raise ImmichPaginationDriftError("bootstrap membership drift")
        yield  # pragma: no cover

    adapter.full_facts = fail_full()
    service = ImmichIncrementalSync(
        adapter, engine, state_repository, clock=lambda: T1
    )

    with pytest.raises(ImmichPaginationDriftError, match="membership drift"):
        service.bootstrap()
    state = state_repository.read(
        adapter.provider_name, IMMICH_INCREMENTAL_MECHANISM
    )
    assert state is not None
    assert state.checkpoint is None
    assert state.version == 0
    assert state.reconciliation_required is False


def test_malformed_immich_checkpoint_marks_reconciliation_required(context):
    adapter, _, state_repository, engine = context
    initial = state_repository.get_or_create(
        adapter.provider_name, IMMICH_INCREMENTAL_MECHANISM
    )
    advanced = state_repository.compare_and_swap_checkpoint(
        adapter.provider_name,
        IMMICH_INCREMENTAL_MECHANISM,
        expected_version=initial.version,
        checkpoint="not-a-timestamp",
    )
    assert advanced is not None
    service = ImmichIncrementalSync(
        adapter, engine, state_repository, clock=lambda: T1
    )

    with pytest.raises(
        InvalidCheckpointError, match="Immich checkpoint"
    ):
        service.run_incremental()

    state = state_repository.read(
        adapter.provider_name, IMMICH_INCREMENTAL_MECHANISM
    )
    assert state is not None
    assert state.checkpoint == "not-a-timestamp"
    assert state.reconciliation_required is True
    assert state.version == advanced.version + 1


def test_full_reconciliation_deactivates_source_outside_observation_scope(
    context,
):
    adapter, repository, _, engine = context
    adapter.full_facts = (
        _fact(adapter.provider_name, "a"),
        _fact(adapter.provider_name, "b"),
    )
    engine.sync_once()
    adapter.full_facts = (_fact(adapter.provider_name, "a"),)

    engine.sync_once()

    source_a = repository.find_source(adapter.provider_name, "a")
    source_b = repository.find_source(adapter.provider_name, "b")
    assert source_a is not None and source_a.is_active is True
    assert source_b is not None and source_b.is_active is False
    assert source_b.deleted_at is not None


def test_source_returning_to_api_key_scope_reuses_identity(context):
    adapter, repository, state_repository, engine = context
    adapter.full_facts = (_fact(adapter.provider_name, "a"),)
    engine.sync_once()
    original = repository.find_source(adapter.provider_name, "a")
    assert original is not None
    original_id = original.id
    original_blob_id = original.blob_id
    assert original_blob_id is not None
    original_blob = repository.get_blob(original_blob_id)
    assert original_blob is not None
    original_asset_id = original_blob.asset_id

    _initialize_checkpoint(state_repository, adapter.provider_name)
    adapter.incremental_facts = ()
    ImmichIncrementalSync(
        adapter, engine, state_repository, clock=lambda: T1
    ).run_incremental()
    still_active = repository.find_source(adapter.provider_name, "a")
    assert still_active is not None and still_active.is_active is True

    adapter.full_facts = ()
    engine.sync_once()
    outside_scope = repository.find_source(adapter.provider_name, "a")
    assert outside_scope is not None
    assert outside_scope.is_active is False
    assert outside_scope.deleted_at is not None

    adapter.full_facts = (_fact(adapter.provider_name, "a"),)
    engine.sync_once()
    returned = repository.find_source(adapter.provider_name, "a")
    assert returned is not None
    assert returned.id == original_id
    assert returned.blob_id == original_blob_id
    assert returned.is_active is True
    assert returned.deleted_at is None
    returned_blob = repository.get_blob(returned.blob_id)
    assert returned_blob is not None
    assert returned_blob.asset_id == original_asset_id


def test_full_pagination_drift_prevents_missing_reconciliation(context):
    adapter, repository, _, engine = context
    adapter.full_facts = (
        _fact(adapter.provider_name, "a"),
        _fact(adapter.provider_name, "b"),
    )
    engine.sync_once()

    def drifting_full():
        yield _fact(adapter.provider_name, "a")
        raise ImmichPaginationDriftError("unique count drift")

    adapter.full_facts = drifting_full()
    with pytest.raises(ImmichPaginationDriftError, match="count drift"):
        engine.sync_once()

    source_b = repository.find_source(adapter.provider_name, "b")
    assert source_b is not None
    assert source_b.is_active is True
    assert source_b.deleted_at is None
