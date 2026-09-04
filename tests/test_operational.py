import fcntl
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pdi.data_status import PipelineErrorCode, PipelineKind
from pdi.operational import (
    LOCK_TIMEOUT_EXIT_CODE,
    PIPELINE_COMMANDS,
    _execute_with_ledger,
    run_formal_pipeline,
)


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class RecordingRepository:
    def __init__(self, events) -> None:
        self.events = events
        self.run = SimpleNamespace(id=uuid4())

    def fail_interrupted_run(self, key):
        self.events.append(("recover", key))

    def begin_run(self, key, kind):
        self.events.append(("begin", key, kind))
        return self.run

    def complete_run(self, run_id):
        self.events.append(("complete", run_id))

    def fail_run(self, run_id, code):
        self.events.append(("fail", run_id, code))


def _run(tmp_path, exit_code=0):
    events = []
    engine = FakeEngine()
    repository = RecordingRepository(events)
    result = run_formal_pipeline(
        "provider.nextcloud.sync",
        lock_timeout=0,
        lock_path=tmp_path / "formal.lock",
        engine_factory=lambda url: engine,
        database_url_loader=lambda: "isolated-db",
        repository_factory=lambda configured_engine: repository,
        command_runner=lambda command: (
            events.append(("command", tuple(command))) or exit_code
        ),
    )
    return result, events, engine


def test_success_recovers_after_lock_then_begins_and_completes(tmp_path) -> None:
    result, events, engine = _run(tmp_path)
    assert result == 0
    assert [event[0] for event in events] == [
        "recover", "begin", "command", "complete"
    ]
    assert events[1][2] is PipelineKind.PROVIDER_SYNC
    assert events[2][1][1:] == PIPELINE_COMMANDS["provider.nextcloud.sync"]
    assert engine.disposed is True


@pytest.mark.parametrize(
    "pipeline_key",
    [
        "provider.nextcloud.incremental",
        "provider.nextcloud.bootstrap",
        "provider.nextcloud.recovery",
        "provider.immich.incremental",
        "provider.immich.bootstrap",
        "provider.immich.recovery",
    ],
)
def test_all_provider_operations_use_same_formal_lock_and_ledger(
    tmp_path, pipeline_key
) -> None:
    events = []
    engine = FakeEngine()
    repository = RecordingRepository(events)
    result = run_formal_pipeline(
        pipeline_key,
        lock_timeout=0,
        lock_path=tmp_path / "same-formal.lock",
        engine_factory=lambda url: engine,
        database_url_loader=lambda: "isolated-db",
        repository_factory=lambda configured_engine: repository,
        command_runner=lambda command: (
            events.append(("command", tuple(command))) or 0
        ),
    )
    assert result == 0
    assert [event[0] for event in events] == [
        "recover", "begin", "command", "complete"
    ]
    assert events[1][1] == pipeline_key
    assert events[1][2] is PipelineKind.PROVIDER_SYNC
    assert events[2][1][1:] == PIPELINE_COMMANDS[pipeline_key]


def test_nonzero_and_exception_fail_with_sanitized_code(tmp_path) -> None:
    result, events, _ = _run(tmp_path, exit_code=9)
    assert result == 9
    assert events[-1][0:1] == ("fail",)
    assert events[-1][2] is PipelineErrorCode.EXECUTION_FAILED

    with pytest.raises(RuntimeError, match="boom"):
        run_formal_pipeline(
            "provider.nextcloud.sync",
            lock_timeout=0,
            lock_path=tmp_path / "exception.lock",
            engine_factory=lambda url: FakeEngine(),
            database_url_loader=lambda: "isolated-db",
            repository_factory=lambda engine: RecordingRepository(events),
            command_runner=lambda command: (_ for _ in ()).throw(
                RuntimeError("boom")
            ),
        )
    assert events[-1][2] is PipelineErrorCode.EXECUTION_FAILED


def test_lock_timeout_creates_no_engine_or_ledger(tmp_path) -> None:
    lock_path = tmp_path / "formal.lock"
    with lock_path.open("a+b") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        called = False

        def engine_factory(url):
            nonlocal called
            called = True
            return FakeEngine()

        result = run_formal_pipeline(
            "provider.nextcloud.sync",
            lock_timeout=0,
            lock_path=lock_path,
            engine_factory=engine_factory,
            database_url_loader=lambda: "isolated-db",
        )
    assert result == LOCK_TIMEOUT_EXIT_CODE
    assert called is False


def test_database_failure_before_begin_creates_no_fabricated_failure(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="database unavailable"):
        run_formal_pipeline(
            "provider.nextcloud.sync",
            lock_timeout=0,
            lock_path=tmp_path / "formal.lock",
            engine_factory=lambda url: (_ for _ in ()).throw(
                RuntimeError("database unavailable")
            ),
            database_url_loader=lambda: "isolated-db",
        )


def test_terminal_update_failure_leaves_recoverable_running_state(tmp_path) -> None:
    events = []
    repository = RecordingRepository(events)

    def fail_terminal(run_id):
        events.append(("terminal_update_failed", run_id))
        raise RuntimeError("terminal database unavailable")

    repository.complete_run = fail_terminal
    with pytest.raises(RuntimeError, match="terminal database unavailable"):
        run_formal_pipeline(
            "provider.nextcloud.sync",
            lock_timeout=0,
            lock_path=tmp_path / "formal.lock",
            engine_factory=lambda url: FakeEngine(),
            database_url_loader=lambda: "isolated-db",
            repository_factory=lambda engine: repository,
            command_runner=lambda command: 0,
        )
    assert [event[0] for event in events] == [
        "recover", "begin", "terminal_update_failed"
    ]


def test_recovery_requires_private_acquired_lock_token() -> None:
    with pytest.raises(RuntimeError, match="acquired formal lock"):
        _execute_with_ledger(
            "provider.nextcloud.sync",
            object(),
            RecordingRepository([]),
            lambda command: 0,
        )


def test_bare_cli_modules_do_not_import_operational_runner() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in ("src/pdi/main.py", "src/pdi/enrichment.py"):
        source = (root / relative).read_text()
        assert "pdi.operational" not in source
        assert "PipelineRun" not in source
        assert "pdi-sync.lock" not in source
