from collections.abc import Callable
from datetime import UTC, datetime

from .errors import DataStatusUnavailableError
from .models import PipelineStatusView, StatusSnapshot
from .registry import PIPELINES, PipelineDefinition
from .repository import PipelineRunRepository


class DataStatusService:
    def __init__(
        self,
        repository: PipelineRunRepository,
        *,
        pipelines: tuple[PipelineDefinition, ...] = PIPELINES,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._pipelines = pipelines
        self._clock = clock or (lambda: datetime.now(UTC))

    def get_status(self) -> StatusSnapshot:
        generated_at = self._clock()
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        generated_at = generated_at.astimezone(UTC)
        keys = tuple(pipeline.pipeline_key for pipeline in self._pipelines)
        try:
            latest = self._repository.get_latest_runs(keys)
            successes = self._repository.get_last_successes(keys)
        except Exception as error:
            raise DataStatusUnavailableError(
                "PDI data status is unavailable"
            ) from error
        views = []
        for pipeline in self._pipelines:
            latest_run = latest.get(pipeline.pipeline_key)
            last_success = successes.get(pipeline.pipeline_key)
            age = None
            if last_success is not None and last_success <= generated_at:
                age = (generated_at - last_success).total_seconds()
            if not pipeline.dependencies:
                validated = None
            else:
                dependency_successes = [
                    successes.get(dependency)
                    for dependency in pipeline.dependencies
                ]
                validated = bool(
                    last_success is not None
                    and all(value is not None for value in dependency_successes)
                    and all(
                        last_success >= value
                        for value in dependency_successes
                        if value is not None
                    )
                )
            views.append(
                PipelineStatusView(
                    pipeline_key=pipeline.pipeline_key,
                    kind=pipeline.kind,
                    latest_status=(latest_run.status if latest_run else None),
                    latest_started_at=(
                        latest_run.started_at if latest_run else None
                    ),
                    latest_finished_at=(
                        latest_run.finished_at if latest_run else None
                    ),
                    latest_error_code=(
                        latest_run.error_code if latest_run else None
                    ),
                    last_success_at=last_success,
                    success_age_seconds=age,
                    dependencies=pipeline.dependencies,
                    validated_after_dependencies=validated,
                )
            )
        return StatusSnapshot(generated_at, tuple(views))
