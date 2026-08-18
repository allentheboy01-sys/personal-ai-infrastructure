from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from pdi.data_status import (
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
        "provider.immich.sync",
        "enrichment.nextcloud_text",
        "enrichment.nextcloud_documents",
        "enrichment.file_metadata",
        "enrichment.immich_geo",
        "enrichment.immich_metadata",
        "enrichment.immich_ocr",
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
    assert len(snapshot.pipelines) == 8
    assert len(repository.calls) == 2
    assert all(len(call[1]) == 8 for call in repository.calls)
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
        latest={"enrichment.nextcloud_text": failed},
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
