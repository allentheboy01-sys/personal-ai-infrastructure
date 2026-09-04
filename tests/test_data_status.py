from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pdi.data_status import (
    FORMAL_PIPELINE_REGISTRY,
    PIPELINES,
    PipelineDefinition,
    PipelineErrorCode,
    PipelineKind,
    PipelineRun,
    PipelineStatus,
    DataStatusService,
    DataStatusUnavailableError,
)
from pdi.data_status.registry import validate_registry


NOW = datetime(2026, 8, 18, 6, tzinfo=UTC)


class FakeRepository:
    def __init__(self, latest=None, successes=None) -> None:
        self.latest = latest or {}
        self.successes = successes or {}
        self.calls = []

    def get_latest_runs(self, keys):
        self.calls.append(("latest", tuple(keys)))
        return self.latest

    def get_last_successes(self, keys):
        self.calls.append(("successes", tuple(keys)))
        return self.successes


def _run(key, status, started, finished=None, error=None):
    return PipelineRun(
        uuid4(), key, PipelineKind.PROVIDER_SYNC, status,
        started, finished, error,
    )


def test_registry_has_frozen_keys_kinds_dependencies_and_generators() -> None:
    by_key = {pipeline.pipeline_key: pipeline for pipeline in PIPELINES}
    assert tuple(by_key) == (
        "provider.nextcloud.sync",
        "provider.nextcloud.incremental",
        "provider.immich.sync",
        "provider.immich.incremental",
        "provider.gmail.sync",
        "enrichment.nextcloud_text",
        "enrichment.nextcloud_documents",
        "enrichment.file_metadata",
        "enrichment.immich_geo",
        "enrichment.immich_metadata",
        "enrichment.immich_ocr",
        "enrichment.gmail_metadata",
    )
    assert {pipeline.kind for pipeline in PIPELINES} == {
        PipelineKind.PROVIDER_SYNC,
        PipelineKind.ENRICHMENT,
    }
    assert by_key["enrichment.file_metadata"].dependencies == (
        "provider.nextcloud.sync", "provider.immich.sync"
    )
    documents = by_key["enrichment.nextcloud_documents"]
    assert tuple(
        generator.generator_name
        for generator in documents.enrichment_generators
    ) == ("nextcloud_pdf", "nextcloud_odt", "nextcloud_docx")
    assert by_key["enrichment.gmail_metadata"].dependencies == (
        "provider.gmail.sync",
    )
    assert "provider.nextcloud.bootstrap" not in by_key
    assert "provider.nextcloud.recovery" not in by_key
    assert {
        "provider.nextcloud.bootstrap",
        "provider.nextcloud.recovery",
        "provider.immich.bootstrap",
        "provider.immich.recovery",
    } <= set(FORMAL_PIPELINE_REGISTRY)


@pytest.mark.parametrize(
    "pipelines, message",
    [
        (
            (
                PipelineDefinition("a", PipelineKind.ENRICHMENT),
                PipelineDefinition("a", PipelineKind.ENRICHMENT),
            ),
            "unique",
        ),
        (
            (PipelineDefinition("a", PipelineKind.ENRICHMENT, ("b",)),),
            "unknown",
        ),
        (
            (PipelineDefinition("a", PipelineKind.ENRICHMENT, ("a",)),),
            "itself",
        ),
        (
            (
                PipelineDefinition("a", PipelineKind.ENRICHMENT, ("b",)),
                PipelineDefinition("b", PipelineKind.ENRICHMENT, ("a",)),
            ),
            "cycle",
        ),
    ],
)
def test_registry_rejects_invalid_graphs(pipelines, message) -> None:
    with pytest.raises(ValueError, match=message):
        validate_registry(pipelines)


def test_empty_status_snapshot_is_bounded_and_uses_two_batch_reads() -> None:
    repository = FakeRepository()
    snapshot = DataStatusService(repository, clock=lambda: NOW).get_status()
    assert snapshot.generated_at == NOW
    assert len(snapshot.pipelines) == 12
    assert len(repository.calls) == 2
    assert all(len(call[1]) == 16 for call in repository.calls)
    roots = [item for item in snapshot.pipelines if not item.dependencies]
    dependents = [item for item in snapshot.pipelines if item.dependencies]
    assert all(item.latest_status is None for item in snapshot.pipelines)
    assert all(item.last_success_at is None for item in snapshot.pipelines)
    assert all(item.validated_after_dependencies is None for item in roots)
    assert all(item.validated_after_dependencies is False for item in dependents)


def test_age_dependency_and_latest_failure_are_independent() -> None:
    nextcloud_success = NOW - timedelta(hours=2)
    text_success = NOW - timedelta(hours=1)
    failed = _run(
        "enrichment.nextcloud_text",
        PipelineStatus.FAILED,
        NOW - timedelta(minutes=10),
        NOW - timedelta(minutes=9),
        PipelineErrorCode.EXECUTION_FAILED,
    )
    repository = FakeRepository(
        latest={
            "provider.nextcloud.sync": _run(
                "provider.nextcloud.sync",
                PipelineStatus.COMPLETED,
                nextcloud_success - timedelta(minutes=1),
                nextcloud_success,
            ),
            "enrichment.nextcloud_text": failed,
        },
        successes={
            "provider.nextcloud.sync": nextcloud_success,
            "enrichment.nextcloud_text": text_success,
        },
    )
    snapshot = DataStatusService(repository, clock=lambda: NOW).get_status()
    text = next(
        item for item in snapshot.pipelines
        if item.pipeline_key == "enrichment.nextcloud_text"
    )
    assert text.latest_status is PipelineStatus.FAILED
    assert text.latest_error_code is PipelineErrorCode.EXECUTION_FAILED
    assert text.last_success_at == text_success
    assert text.success_age_seconds == 3600
    assert text.validated_after_dependencies is True


def test_provider_mutation_attempts_conservatively_invalidate_enrichment() -> None:
    full_success = NOW - timedelta(hours=2)
    enrichment_success = NOW - timedelta(minutes=90)
    incremental_success = NOW - timedelta(hours=1)
    repository = FakeRepository(
        latest={
            "provider.nextcloud.incremental": _run(
                "provider.nextcloud.incremental",
                PipelineStatus.COMPLETED,
                incremental_success - timedelta(minutes=1),
                incremental_success,
            )
        },
        successes={
            "provider.nextcloud.sync": full_success,
            "provider.nextcloud.incremental": incremental_success,
            "enrichment.nextcloud_text": enrichment_success,
        },
    )
    snapshot = DataStatusService(repository, clock=lambda: NOW).get_status()
    text = next(
        item for item in snapshot.pipelines
        if item.pipeline_key == "enrichment.nextcloud_text"
    )
    assert text.validated_after_dependencies is False

    repository.successes["enrichment.nextcloud_text"] = NOW
    snapshot = DataStatusService(repository, clock=lambda: NOW).get_status()
    text = next(
        item for item in snapshot.pipelines
        if item.pipeline_key == "enrichment.nextcloud_text"
    )
    assert text.validated_after_dependencies is True


@pytest.mark.parametrize(
    ("key", "status"),
    [
        ("provider.nextcloud.incremental", PipelineStatus.RUNNING),
        ("provider.nextcloud.incremental", PipelineStatus.FAILED),
        ("provider.nextcloud.bootstrap", PipelineStatus.COMPLETED),
        ("provider.nextcloud.recovery", PipelineStatus.COMPLETED),
        ("provider.nextcloud.bootstrap", PipelineStatus.FAILED),
        ("provider.nextcloud.recovery", PipelineStatus.FAILED),
    ],
)
def test_latest_provider_mutation_watermark_includes_all_formal_attempts(
    key, status
) -> None:
    attempt_at = NOW - timedelta(minutes=10)
    enrichment_success = NOW - timedelta(minutes=20)
    finished = None if status is PipelineStatus.RUNNING else attempt_at
    successes = {
        "provider.nextcloud.sync": NOW - timedelta(hours=2),
        "enrichment.nextcloud_text": enrichment_success,
    }
    if status is PipelineStatus.COMPLETED:
        successes[key] = attempt_at
    repository = FakeRepository(
        latest={
            key: _run(key, status, attempt_at, finished)
        },
        successes=successes,
    )
    snapshot = DataStatusService(repository, clock=lambda: NOW).get_status()
    text = next(
        item for item in snapshot.pipelines
        if item.pipeline_key == "enrichment.nextcloud_text"
    )
    assert text.validated_after_dependencies is False


def test_provider_group_requires_at_least_one_formal_success() -> None:
    repository = FakeRepository(
        latest={
            "provider.nextcloud.incremental": _run(
                "provider.nextcloud.incremental",
                PipelineStatus.FAILED,
                NOW - timedelta(minutes=10),
                NOW - timedelta(minutes=9),
            )
        },
        successes={"enrichment.nextcloud_text": NOW},
    )
    snapshot = DataStatusService(repository, clock=lambda: NOW).get_status()
    text = next(
        item for item in snapshot.pipelines
        if item.pipeline_key == "enrichment.nextcloud_text"
    )
    assert text.validated_after_dependencies is False


def test_provider_sync_state_health_is_bounded_and_checkpoint_redacted() -> None:
    class StateRepository:
        def read(self, provider, mechanism):
            if provider == "nextcloud":
                return None
            return SimpleNamespace(
                checkpoint="secret-opaque-watermark",
                version=7,
                reconciliation_required=True,
                updated_at=NOW - timedelta(minutes=2),
            )

    snapshot = DataStatusService(
        FakeRepository(),
        sync_state_repository=StateRepository(),
        clock=lambda: NOW,
    ).get_status()
    nextcloud, immich = snapshot.provider_sync_states
    assert nextcloud.state_exists is False
    assert nextcloud.checkpoint_initialized is False
    assert nextcloud.version is None
    assert nextcloud.reconciliation_required is None
    assert immich.state_exists is True
    assert immich.checkpoint_initialized is True
    assert immich.version == 7
    assert immich.reconciliation_required is True
    assert not hasattr(immich, "checkpoint")


def test_null_checkpoint_is_existing_but_uninitialized() -> None:
    class StateRepository:
        def read(self, provider, mechanism):
            return SimpleNamespace(
                checkpoint=None,
                version=0,
                reconciliation_required=False,
                updated_at=NOW,
            )

    snapshot = DataStatusService(
        FakeRepository(),
        sync_state_repository=StateRepository(),
        clock=lambda: NOW,
    ).get_status()
    assert all(state.state_exists for state in snapshot.provider_sync_states)
    assert all(
        not state.checkpoint_initialized
        for state in snapshot.provider_sync_states
    )


def test_future_success_has_null_age_and_raw_timestamp() -> None:
    future = NOW + timedelta(seconds=1)
    repository = FakeRepository(
        successes={"provider.nextcloud.sync": future}
    )
    snapshot = DataStatusService(repository, clock=lambda: NOW).get_status()
    pipeline = snapshot.pipelines[0]
    assert pipeline.last_success_at == future
    assert pipeline.success_age_seconds is None


def test_repository_failure_is_sanitized_by_service() -> None:
    class FailingRepository(FakeRepository):
        def get_latest_runs(self, keys):
            raise RuntimeError("postgresql://user:secret@private-host/pdi")

    with pytest.raises(
        DataStatusUnavailableError,
        match="PDI data status is unavailable",
    ) as captured:
        DataStatusService(FailingRepository(), clock=lambda: NOW).get_status()
    assert "private-host" not in str(captured.value)


def test_status_rejects_naive_generated_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        DataStatusService(
            FakeRepository(),
            clock=lambda: datetime(2026, 8, 18, 6),
        ).get_status()
