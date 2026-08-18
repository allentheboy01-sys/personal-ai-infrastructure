import argparse
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from sqlalchemy import Engine

from pdi.config.settings import load_database_url
from pdi.data_status import (
    PIPELINE_REGISTRY,
    PipelineErrorCode,
    PipelineRunRepository,
)
from pdi.database import create_postgres_engine


logger = logging.getLogger(__name__)
LOCK_PATH = Path("/run/lock/pdi-sync.lock")
LOCK_TIMEOUT_EXIT_CODE = 75
CHILD_TERMINATION_GRACE_SECONDS = 10.0


PIPELINE_COMMANDS: dict[str, tuple[str, ...]] = {
    "provider.nextcloud.sync": ("-m", "pdi.main", "--provider", "nextcloud"),
    "provider.immich.sync": ("-m", "pdi.main", "--provider", "immich"),
    "enrichment.nextcloud_text": (
        "-m", "pdi.enrichment", "--extractor", "nextcloud-text",
        "--batch-size", "100",
    ),
    "enrichment.nextcloud_documents": (
        "-m", "pdi.enrichment", "--extractor", "nextcloud-documents",
        "--batch-size", "100",
    ),
    "enrichment.file_metadata": (
        "-m", "pdi.enrichment", "--extractor", "file-metadata",
        "--batch-size", "20000",
    ),
    "enrichment.immich_geo": (
        "-m", "pdi.enrichment", "--extractor", "immich-geo",
        "--batch-size", "20000",
    ),
    "enrichment.immich_metadata": (
        "-m", "pdi.enrichment", "--batch-size", "20000",
    ),
    "enrichment.immich_ocr": (
        "-m", "pdi.enrichment", "--extractor", "immich-ocr",
        "--batch-size", "20000",
    ),
}

if set(PIPELINE_COMMANDS) != set(PIPELINE_REGISTRY):
    raise RuntimeError("formal command map must match pipeline registry")


class LockTimeoutError(RuntimeError):
    pass


class RunnerInterrupted(BaseException):
    def __init__(self, signum: int) -> None:
        self.signum = signum
        super().__init__(f"formal runner interrupted by signal {signum}")


@dataclass(frozen=True)
class _AcquiredFormalLock:
    path: Path


@contextmanager
def acquire_formal_lock(
    path: Path,
    timeout_seconds: float,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
):
    if timeout_seconds < 0:
        raise ValueError("lock timeout must be non-negative")
    deadline = monotonic() + timeout_seconds
    with path.open("a+b") as lock_file:
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if monotonic() >= deadline:
                    raise LockTimeoutError("formal pipeline lock timed out")
                sleep(min(0.1, max(0.0, deadline - monotonic())))
        try:
            yield _AcquiredFormalLock(path)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _terminate_and_reap(
    process: subprocess.Popen,
    signum: int,
    *,
    grace_seconds: float = CHILD_TERMINATION_GRACE_SECONDS,
) -> None:
    if process.poll() is not None:
        process.wait()
        return
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_child_process(command: Sequence[str]) -> int:
    process = subprocess.Popen(command, start_new_session=True)
    previous_handlers: dict[int, object] = {}

    def interrupt(signum, frame) -> None:
        raise RunnerInterrupted(signum)

    for signum in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, interrupt)
    try:
        try:
            return process.wait()
        except RunnerInterrupted as interruption:
            _terminate_and_reap(process, interruption.signum)
            raise
        except KeyboardInterrupt:
            _terminate_and_reap(process, signal.SIGINT)
            raise
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def _execute_with_ledger(
    pipeline_key: str,
    lock: _AcquiredFormalLock,
    repository: PipelineRunRepository,
    command_runner: Callable[[Sequence[str]], int],
) -> int:
    if not isinstance(lock, _AcquiredFormalLock):
        raise RuntimeError("interrupted recovery requires an acquired formal lock")
    definition = PIPELINE_REGISTRY[pipeline_key]
    repository.fail_interrupted_run(pipeline_key)
    run = repository.begin_run(pipeline_key, definition.kind)
    try:
        exit_code = command_runner((sys.executable, *PIPELINE_COMMANDS[pipeline_key]))
    except BaseException:
        repository.fail_run(run.id, PipelineErrorCode.EXECUTION_FAILED)
        raise
    if exit_code == 0:
        repository.complete_run(run.id)
    else:
        repository.fail_run(run.id, PipelineErrorCode.EXECUTION_FAILED)
    return exit_code


def run_formal_pipeline(
    pipeline_key: str,
    *,
    lock_timeout: float,
    lock_path: Path = LOCK_PATH,
    engine_factory: Callable[[str], Engine] = create_postgres_engine,
    database_url_loader: Callable[[], str] = load_database_url,
    repository_factory: Callable[[Engine], PipelineRunRepository] = (
        PipelineRunRepository
    ),
    command_runner: Callable[[Sequence[str]], int] = run_child_process,
) -> int:
    if pipeline_key not in PIPELINE_REGISTRY:
        raise ValueError(f"unknown formal pipeline: {pipeline_key}")
    try:
        with acquire_formal_lock(lock_path, lock_timeout) as lock:
            engine = engine_factory(database_url_loader())
            try:
                repository = repository_factory(engine)
                return _execute_with_ledger(
                    pipeline_key,
                    lock,
                    repository,
                    command_runner,
                )
            finally:
                engine.dispose()
    except LockTimeoutError:
        logger.error("Formal pipeline lock acquisition timed out")
        return LOCK_TIMEOUT_EXIT_CODE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one registered PDI pipeline under the formal lock."
    )
    parser.add_argument(
        "--pipeline-key",
        required=True,
        choices=tuple(PIPELINE_REGISTRY),
    )
    parser.add_argument("--lock-timeout", type=float, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_formal_pipeline(
            args.pipeline_key,
            lock_timeout=args.lock_timeout,
        )
    except RunnerInterrupted as interruption:
        return 128 + interruption.signum
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
