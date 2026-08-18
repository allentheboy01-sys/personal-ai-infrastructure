from datetime import UTC, datetime
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from tests.integration.database_guard import require_safe_test_database_url


def _wait_for(predicate, *, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("timed out waiting for controlled process state")
        time.sleep(0.02)


def _runner_command(
    lock_path: Path,
    prefix: Path,
    *,
    shutdown_delay: float,
    run_seconds: float,
    lock_timeout: float = 5.0,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "tests.fixtures.formal_runner_harness",
        "--lock-path",
        str(lock_path),
        "--lock-timeout",
        str(lock_timeout),
        "--pid-file",
        str(prefix.with_suffix(".pid")),
        "--entered-file",
        str(prefix.with_suffix(".entered")),
        "--terminating-file",
        str(prefix.with_suffix(".terminating")),
        "--exited-file",
        str(prefix.with_suffix(".exited")),
        "--shutdown-delay",
        str(shutdown_delay),
        "--run-seconds",
        str(run_seconds),
    ]


@pytest.fixture
def interruption_database(monkeypatch):
    database_url = require_safe_test_database_url()
    engine = create_engine(database_url, poolclass=NullPool)
    config = Config("alembic.ini")
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM pipeline_runs"))
    environment = os.environ.copy()
    environment["DATABASE__URL"] = database_url
    try:
        yield engine, environment
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM pipeline_runs"))
        engine.dispose()


@pytest.mark.parametrize("interrupt_signal", [signal.SIGTERM, signal.SIGINT])
def test_runner_interrupt_terminates_reaps_and_fails_child(
    interruption_database,
    tmp_path,
    interrupt_signal,
) -> None:
    engine, environment = interruption_database
    lock_path = tmp_path / "formal.lock"
    first = tmp_path / "first"
    runner = subprocess.Popen(
        _runner_command(
            lock_path,
            first,
            shutdown_delay=0.25,
            run_seconds=30,
        ),
        env=environment,
    )
    _wait_for(lambda: first.with_suffix(".entered").exists())
    child_pid = int(first.with_suffix(".pid").read_text())
    with engine.connect() as connection:
        _wait_for(
            lambda: connection.execute(
                text(
                    "SELECT count(*) FROM pipeline_runs "
                    "WHERE status='running'"
                )
            ).scalar_one()
            == 1
        )

    runner.send_signal(interrupt_signal)
    assert runner.wait(timeout=10) != 0
    assert first.with_suffix(".terminating").exists()
    assert first.with_suffix(".exited").exists()
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT status,error_code,finished_at "
                "FROM pipeline_runs ORDER BY started_at DESC LIMIT 1"
            )
        ).one()
    assert row.status == "failed"
    assert row.error_code == "execution_failed"
    assert row.finished_at.tzinfo is not None


def test_second_runner_enters_only_after_first_child_exits(
    interruption_database,
    tmp_path,
) -> None:
    engine, environment = interruption_database
    lock_path = tmp_path / "formal.lock"
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_runner = subprocess.Popen(
        _runner_command(
            lock_path,
            first,
            shutdown_delay=1.0,
            run_seconds=30,
        ),
        env=environment,
    )
    _wait_for(lambda: first.with_suffix(".entered").exists())
    first_runner.send_signal(signal.SIGTERM)
    _wait_for(lambda: first.with_suffix(".terminating").exists())

    second_runner = subprocess.Popen(
        _runner_command(
            lock_path,
            second,
            shutdown_delay=0,
            run_seconds=0,
        ),
        env=environment,
    )
    time.sleep(0.2)
    assert not second.with_suffix(".entered").exists()
    assert first_runner.poll() is None

    assert first_runner.wait(timeout=10) != 0
    assert second_runner.wait(timeout=10) == 0
    first_exited_at = float(first.with_suffix(".exited").read_text())
    second_entered_at = float(second.with_suffix(".entered").read_text())
    assert second_entered_at >= first_exited_at
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT status,error_code FROM pipeline_runs "
                "ORDER BY started_at"
            )
        ).all()
    assert rows == [("failed", "execution_failed"), ("completed", None)]
