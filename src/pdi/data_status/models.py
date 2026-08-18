from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class PipelineKind(StrEnum):
    PROVIDER_SYNC = "provider_sync"
    ENRICHMENT = "enrichment"


class PipelineStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineErrorCode(StrEnum):
    EXECUTION_FAILED = "execution_failed"
    INTERRUPTED_PREVIOUS_RUN = "interrupted_previous_run"


@dataclass(frozen=True)
class PipelineRun:
    id: UUID
    pipeline_key: str
    kind: PipelineKind
    status: PipelineStatus
    started_at: datetime
    finished_at: datetime | None
    error_code: PipelineErrorCode | None


@dataclass(frozen=True)
class PipelineStatusView:
    pipeline_key: str
    kind: PipelineKind
    latest_status: PipelineStatus | None
    latest_started_at: datetime | None
    latest_finished_at: datetime | None
    latest_error_code: PipelineErrorCode | None
    last_success_at: datetime | None
    success_age_seconds: float | None
    dependencies: tuple[str, ...]
    validated_after_dependencies: bool | None


@dataclass(frozen=True)
class StatusSnapshot:
    generated_at: datetime
    pipelines: tuple[PipelineStatusView, ...]
