from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Connection, func, select

from pdi.adapters.base import ProviderFact
from pdi.database import create_postgres_engine
from pdi.engine import (
    DiscoveryBatch,
    DiscoveryMode,
    InvalidCheckpointError,
    ReconciliationRequiredError,
    SyncEngine,
)
from pdi.identity import Matcher
from pdi.repository import PostgreSQLRepository
from pdi.repository.orm.asset import AssetORM
from pdi.repository.orm.provider_sync_state import ProviderSyncStateORM
from pdi.sync_state import PostgreSQLProviderSyncStateRepository
from tests.integration.database_guard import require_safe_test_database_url


ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture
def state_context():
    engine = create_postgres_engine(require_safe_test_database_url())
    with engine.connect() as connection:
        command.upgrade(_alembic_config(connection), "head")
    try:
        yield engine, PostgreSQLProviderSyncStateRepository(engine)
    finally:
        engine.dispose()


def test_state_create_read_cas_and_stale_writer_rejection(state_context) -> None:
    engine, repository = state_context
    provider = f"state-provider-{uuid4()}"
    mechanism = "fake-window"
    with engine.connect() as connection:
        business_rows_before = connection.execute(
            select(func.count()).select_from(AssetORM)
        ).scalar_one()

    initial = repository.get_or_create(provider, mechanism)
    assert initial.checkpoint is None
    assert initial.version == 0
    assert initial.reconciliation_required is False
    assert repository.read(provider, mechanism) == initial

    advanced = repository.compare_and_swap_checkpoint(
        provider,
        mechanism,
        expected_version=0,
        checkpoint="checkpoint-b",
    )
    assert advanced is not None
    assert advanced.checkpoint == "checkpoint-b"
    assert advanced.version == 1

    stale = repository.compare_and_swap_checkpoint(
        provider,
        mechanism,
        expected_version=0,
        checkpoint="stale-overwrite",
    )
    assert stale is None
    current = repository.read(provider, mechanism)
    assert current is not None
    assert current.checkpoint == "checkpoint-b"
    assert current.version == 1

    marked = repository.mark_reconciliation_required(
        provider,
        mechanism,
        expected_version=1,
    )
    assert marked is not None
    assert marked.reconciliation_required is True
    assert marked.checkpoint == "checkpoint-b"
    assert marked.version == 2

    with engine.connect() as connection:
        assert connection.execute(
            select(func.count()).select_from(AssetORM)
        ).scalar_one() == business_rows_before
        assert connection.execute(
            select(ProviderSyncStateORM.checkpoint)
            .where(ProviderSyncStateORM.provider == provider)
        ).scalar_one() == "checkpoint-b"


def test_normal_advance_rejects_null_without_mutating_state(
    state_context,
) -> None:
    _, repository = state_context
    provider = f"null-rejection-{uuid4()}"
    mechanism = "fake-window"
    initial = repository.get_or_create(provider, mechanism)
    advanced = repository.compare_and_swap_checkpoint(
        provider,
        mechanism,
        expected_version=initial.version,
        checkpoint="cursor-a",
    )
    assert advanced is not None

    with pytest.raises(ValueError, match="trusted checkpoint"):
        repository.compare_and_swap_checkpoint(
            provider,
            mechanism,
            expected_version=advanced.version,
            checkpoint=None,  # type: ignore[arg-type]
        )

    unchanged = repository.read(provider, mechanism)
    assert unchanged is not None
    assert unchanged.checkpoint == "cursor-a"
    assert unchanged.version == advanced.version


def test_recovery_requires_trusted_checkpoint_and_uses_cas(
    state_context,
) -> None:
    _, repository = state_context
    provider = f"recovery-provider-{uuid4()}"
    mechanism = "fake-window"
    initial = repository.get_or_create(provider, mechanism)
    first = repository.compare_and_swap_checkpoint(
        provider,
        mechanism,
        expected_version=initial.version,
        checkpoint="old",
    )
    assert first is not None
    second = repository.compare_and_swap_checkpoint(
        provider,
        mechanism,
        expected_version=first.version,
        checkpoint="old",
    )
    assert second is not None
    marked = repository.mark_reconciliation_required(
        provider,
        mechanism,
        expected_version=second.version,
    )
    assert marked is not None
    assert marked.version == 3
    assert marked.reconciliation_required is True

    bypass = repository.compare_and_swap_checkpoint(
        provider,
        mechanism,
        expected_version=3,
        checkpoint="must-not-clear-latch",
    )
    assert bypass is None

    recovered = repository.recover_after_reconciliation(
        provider,
        mechanism,
        expected_version=3,
        trusted_checkpoint="fresh",
    )
    assert recovered is not None
    assert recovered.checkpoint == "fresh"
    assert recovered.version == 4
    assert recovered.reconciliation_required is False

    stale = repository.recover_after_reconciliation(
        provider,
        mechanism,
        expected_version=3,
        trusted_checkpoint="stale",
    )
    assert stale is None

    with pytest.raises(ValueError, match="trusted checkpoint"):
        repository.recover_after_reconciliation(
            provider,
            mechanism,
            expected_version=4,
            trusted_checkpoint=None,  # type: ignore[arg-type]
        )

    unchanged = repository.read(provider, mechanism)
    assert unchanged is not None
    assert unchanged.checkpoint == "fresh"
    assert unchanged.version == 4
    assert unchanged.reconciliation_required is False


def _fact(provider: str, external_id: str) -> ProviderFact:
    return ProviderFact(
        provider=provider,
        kind="file",
        external_id=external_id,
        name="replay.txt",
        attributes={
            "path": "replay.txt",
            "size": 4,
            "mime_type": "text/plain",
            "version_tag": "v1",
            "content_hash": None,
        },
        raw={
            "href": "/synthetic/replay.txt",
            "oc_id": external_id,
            "file_id": external_id,
            "is_collection": False,
        },
    )


class _Adapter:
    def __init__(self, provider: str) -> None:
        self.provider_name = provider

    def connect(self) -> None:
        return None

    def scan(self):
        pytest.fail("incremental test must not use full scan")

    def open(self, fact: ProviderFact):
        yield b"data"


def test_checkpoint_is_last_and_failed_window_replays_safely(
    state_context,
) -> None:
    engine, state_repository = state_context
    provider = f"replay-provider-{uuid4()}"
    external_id = f"replay-source-{uuid4()}"
    business_repository = PostgreSQLRepository(engine)
    engine_under_test = SyncEngine(
        _Adapter(provider),
        Matcher(),
        business_repository,
        state_repository,
    )

    def interrupted_facts():
        yield _fact(provider, external_id)
        raise RuntimeError("synthetic failure before checkpoint CAS")

    with pytest.raises(RuntimeError, match="before checkpoint CAS"):
        engine_under_test.sync_incremental(
            "fake-window",
            lambda state: DiscoveryBatch(
                provider=provider,
                mode=DiscoveryMode.INCREMENTAL_NON_AUTHORITATIVE,
                facts=interrupted_facts(),
                next_checkpoint="checkpoint-b",
            ),
        )

    unchanged = state_repository.read(provider, "fake-window")
    assert unchanged is not None
    assert unchanged.checkpoint is None
    assert unchanged.version == 0
    committed = business_repository.find_source(provider, external_id)
    assert committed is not None
    committed_id = committed.id
    blob_id = committed.blob_id

    advanced = engine_under_test.sync_incremental(
        "fake-window",
        lambda state: DiscoveryBatch(
            provider=provider,
            mode=DiscoveryMode.INCREMENTAL_NON_AUTHORITATIVE,
            facts=(_fact(provider, external_id),),
            next_checkpoint="checkpoint-b",
        ),
    )
    replayed = business_repository.find_source(provider, external_id)
    assert replayed is not None
    assert replayed.id == committed_id
    assert replayed.blob_id == blob_id
    assert advanced.checkpoint == "checkpoint-b"
    assert advanced.version == 1


def test_invalid_checkpoint_persists_reconciliation_required(
    state_context,
) -> None:
    _, state_repository = state_context
    provider = f"invalid-provider-{uuid4()}"
    engine_under_test = SyncEngine(
        _Adapter(provider),
        Matcher(),
        PostgreSQLRepository(state_context[0]),
        state_repository,
    )

    def invalid(state):
        raise InvalidCheckpointError("synthetic checkpoint gap")

    with pytest.raises(InvalidCheckpointError, match="checkpoint gap"):
        engine_under_test.sync_incremental("fake-window", invalid)

    state = state_repository.read(provider, "fake-window")
    assert state is not None
    assert state.reconciliation_required is True
    assert state.version == 1
    with pytest.raises(ReconciliationRequiredError):
        engine_under_test.sync_incremental("fake-window", invalid)
