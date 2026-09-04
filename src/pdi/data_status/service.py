from collections.abc import Callable
from datetime import UTC, datetime

from pdi.sync_state import ProviderSyncStateRepository

from .errors import DataStatusUnavailableError
from .models import (
    PipelineStatus,
    PipelineStatusView,
    ProviderSyncStateView,
    StatusSnapshot,
)
from .registry import (
    FORMAL_PIPELINES,
    PIPELINES,
    PROVIDER_MUTATION_GROUPS,
    PROVIDER_SYNC_STATE_TARGETS,
    PipelineDefinition,
)
from .repository import PipelineRunRepository


class DataStatusService:
    def __init__(
        self,
        repository: PipelineRunRepository,
        *,
        pipelines: tuple[PipelineDefinition, ...] = PIPELINES,
        sync_state_repository: ProviderSyncStateRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._pipelines = pipelines
        self._sync_state_repository = sync_state_repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def get_status(self) -> StatusSnapshot:
        generated_at = self._clock()
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        generated_at = generated_at.astimezone(UTC)
        health_keys = tuple(
            pipeline.pipeline_key for pipeline in self._pipelines
        )
        formal_keys = tuple(
            pipeline.pipeline_key for pipeline in FORMAL_PIPELINES
        )
        keys = tuple(dict.fromkeys((*health_keys, *formal_keys)))
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
                dependency_states = []
                for dependency in pipeline.dependencies:
                    group = PROVIDER_MUTATION_GROUPS.get(
                        dependency, (dependency,)
                    )
                    group_successes = [
                        successes[key] for key in group if key in successes
                    ]
                    candidates = []
                    for key in group:
                        run = latest.get(key)
                        if run is None:
                            continue
                        candidate = (
                            run.started_at
                            if run.status is PipelineStatus.RUNNING
                            else run.finished_at
                        )
                        if candidate is not None:
                            candidates.append(candidate)
                    dependency_states.append(
                        (
                            bool(group_successes),
                            max(candidates) if candidates else None,
                        )
                    )
                validated = bool(
                    last_success is not None
                    and all(established for established, _ in dependency_states)
                    and all(
                        watermark is not None and last_success >= watermark
                        for _, watermark in dependency_states
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
        try:
            state_views = []
            for provider, mechanism in PROVIDER_SYNC_STATE_TARGETS:
                state = (
                    None
                    if self._sync_state_repository is None
                    else self._sync_state_repository.read(provider, mechanism)
                )
                state_views.append(
                    ProviderSyncStateView(
                        provider=provider,
                        mechanism=mechanism,
                        state_exists=state is not None,
                        checkpoint_initialized=(
                            state is not None and state.checkpoint is not None
                        ),
                        version=None if state is None else state.version,
                        reconciliation_required=(
                            None
                            if state is None
                            else state.reconciliation_required
                        ),
                        updated_at=(
                            None if state is None else state.updated_at
                        ),
                    )
                )
        except Exception as error:
            raise DataStatusUnavailableError(
                "PDI data status is unavailable"
            ) from error
        return StatusSnapshot(
            generated_at, tuple(views), tuple(state_views)
        )
