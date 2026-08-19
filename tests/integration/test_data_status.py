from datetime import UTC, datetime, timedelta

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool
from uuid import uuid4

from pdi.data_status import (
    PipelineErrorCode,
    PipelineKind,
    PipelineRunLifecycleError,
    PipelineRunRepository,
    PipelineStatus,
)
from pdi.operational import run_formal_pipeline
from tests.integration.database_guard import require_safe_test_database_url


NOW = datetime(2026, 8, 18, 6, tzinfo=UTC)


@pytest.fixture
def ledger():
    engine = create_engine(
        require_safe_test_database_url(), poolclass=NullPool
    )
    config = Config("alembic.ini")
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM pipeline_runs"))
    try:
        yield engine, PipelineRunRepository(engine)
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM pipeline_runs"))
        engine.dispose()


def test_begin_complete_fail_history_latest_and_last_success(ledger) -> None:
    _, repository = ledger
    first = repository.begin_run(
        "provider.nextcloud.sync",
        PipelineKind.PROVIDER_SYNC,
        started_at=NOW,
    )
    completed = repository.complete_run(
        first.id, finished_at=NOW + timedelta(seconds=2)
    )
    second = repository.begin_run(
        "provider.nextcloud.sync",
        PipelineKind.PROVIDER_SYNC,
        started_at=NOW + timedelta(seconds=3),
    )
    failed = repository.fail_run(
        second.id,
        PipelineErrorCode.EXECUTION_FAILED,
        finished_at=NOW + timedelta(seconds=4),
    )
    assert completed.status is PipelineStatus.COMPLETED
    assert failed.status is PipelineStatus.FAILED
    assert repository.get_latest_runs(
        ["provider.nextcloud.sync"]
    ) == {"provider.nextcloud.sync": failed}
    assert repository.get_last_successes(
        ["provider.nextcloud.sync"]
    ) == {"provider.nextcloud.sync": completed.finished_at}


def test_running_uniqueness_and_different_pipeline_concurrency(ledger) -> None:
    _, repository = ledger
    repository.begin_run(
        "provider.nextcloud.sync", PipelineKind.PROVIDER_SYNC,
        started_at=NOW,
    )
    with pytest.raises(IntegrityError):
        repository.begin_run(
            "provider.nextcloud.sync", PipelineKind.PROVIDER_SYNC,
            started_at=NOW,
        )
    other = repository.begin_run(
        "provider.immich.sync", PipelineKind.PROVIDER_SYNC,
        started_at=NOW,
    )
    assert other.status is PipelineStatus.RUNNING


def test_recovery_and_terminal_lifecycle_guard(ledger) -> None:
    _, repository = ledger
    running = repository.begin_run(
        "enrichment.immich_geo", PipelineKind.ENRICHMENT,
        started_at=NOW,
    )
    recovered = repository.fail_interrupted_run(
        "enrichment.immich_geo", finished_at=NOW + timedelta(seconds=1)
    )
    assert recovered is not None
    assert recovered.id == running.id
    assert recovered.error_code is PipelineErrorCode.INTERRUPTED_PREVIOUS_RUN
    assert repository.fail_interrupted_run("enrichment.immich_geo") is None
    with pytest.raises(PipelineRunLifecycleError):
        repository.complete_run(running.id)


def test_clock_rollback_terminal_row_is_persisted(ledger) -> None:
    _, repository = ledger
    run = repository.begin_run(
        "provider.immich.sync", PipelineKind.PROVIDER_SYNC,
        started_at=NOW,
    )
    completed = repository.complete_run(
        run.id, finished_at=NOW - timedelta(seconds=10)
    )
    assert completed.finished_at < completed.started_at


@pytest.mark.parametrize(
    "values",
    [
        {
            "status": "running",
            "finished_at": NOW,
            "error_code": None,
        },
        {
            "status": "completed",
            "finished_at": None,
            "error_code": None,
        },
        {
            "status": "completed",
            "finished_at": NOW,
            "error_code": "execution_failed",
        },
        {
            "status": "failed",
            "finished_at": NOW,
            "error_code": None,
        },
        {
            "status": "failed",
            "finished_at": NOW,
            "error_code": "raw_exception",
        },
    ],
)
def test_database_rejects_incoherent_terminal_states(ledger, values) -> None:
    engine, _ = ledger
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO pipeline_runs "
                "(id,pipeline_key,kind,status,started_at,finished_at,error_code) "
                "VALUES (gen_random_uuid(),'test.pipeline','enrichment',"
                ":status,:started_at,:finished_at,:error_code)"
            ),
            {"started_at": NOW, **values},
        )


def test_begin_is_durable_across_unrelated_rollback(ledger) -> None:
    engine, repository = ledger
    run = repository.begin_run(
        "enrichment.immich_ocr", PipelineKind.ENRICHMENT,
        started_at=NOW,
    )
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("SELECT 1"))
        transaction.rollback()
    latest = repository.get_latest_runs(["enrichment.immich_ocr"])
    assert latest["enrichment.immich_ocr"].id == run.id


def test_fake_provider_partial_commit_maps_nonzero_to_failed_ledger(
    ledger,
    tmp_path,
) -> None:
    engine, repository = ledger
    asset_id = uuid4()

    def fake_provider(command) -> int:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO assets "
                    "(id,resource_type,title,metadata,created_at,updated_at) "
                    "VALUES (:id,'file','fake-provider-partial','{}'::jsonb,now(),now())"
                ),
                {"id": asset_id},
            )
        return 1

    try:
        assert run_formal_pipeline(
            "provider.nextcloud.sync",
            lock_timeout=0,
            lock_path=tmp_path / "formal.lock",
            engine_factory=lambda url: engine,
            database_url_loader=lambda: require_safe_test_database_url(),
            command_runner=fake_provider,
        ) == 1
        latest = repository.get_latest_runs(["provider.nextcloud.sync"])
        assert latest["provider.nextcloud.sync"].status is PipelineStatus.FAILED
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT count(*) FROM assets WHERE id=:id"),
                {"id": asset_id},
            ).scalar_one() == 1
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM assets WHERE id=:id"), {"id": asset_id}
            )
