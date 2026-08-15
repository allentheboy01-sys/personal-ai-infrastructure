from datetime import UTC, datetime, timedelta
from typing import Callable

from .errors import ObservationResourceNotFoundError, ObservationValidationError
from .models import GeneratorIdentity, ObservationBatch, PublishResult, StatementView, WorkerResult
from .predicates import get_predicate
from .repository import ObservationRepository


class ObservationService:
    def __init__(self, repository: ObservationRepository) -> None:
        self._repository = repository

    def publish(self, batch: ObservationBatch, *, completed_at: datetime | None = None) -> PublishResult:
        return self._repository.publish(batch, completed_at=completed_at or datetime.now(UTC))

    def get_resource_statements(self, resource_ref: str, *, predicate: str | None = None, include_history: bool = False, limit: int = 100) -> tuple[StatementView, ...]:
        if predicate is not None:
            get_predicate(predicate)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ObservationValidationError("limit must be between 1 and 100")
        result = self._repository.get_resource_statements(resource_ref, predicate=predicate, include_history=include_history, limit=limit)
        if result is None:
            raise ObservationResourceNotFoundError("Resource does not exist")
        return result


class EnrichmentWorker:
    DEFAULT_STALE_AFTER = timedelta(minutes=30)

    def __init__(self, repository: ObservationRepository, extractor, *, provider: str = "immich", clock: Callable[[], datetime] | None = None, stale_after: timedelta = DEFAULT_STALE_AFTER) -> None:
        self._repository = repository; self._extractor = extractor
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("provider must be non-empty")
        self._provider = provider
        self._clock = clock or (lambda: datetime.now(UTC)); self._stale_after = stale_after

    def run_once(self, *, batch_size: int) -> WorkerResult:
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("batch_size must be positive")
        resources = self._repository.list_enrichment_resources(
            provider=self._provider
        )
        is_eligible = getattr(self._extractor, "is_eligible", None)
        if callable(is_eligible):
            resources = tuple(
                resource
                for resource in resources
                if is_eligible(resource)
            )
        processed = skipped = failed = writes = deactivated = 0
        for resource in resources[:batch_size]:
            try:
                fingerprint = self._extractor.input_fingerprint(resource)
            except Exception:
                failed += 1
                continue
            now = self._clock()
            if not self._repository.mark_running(resource.resource_ref, self._extractor.generator, fingerprint, now=now, stale_after=self._stale_after):
                skipped += 1
                continue
            try:
                batch = self._extractor.extract(resource)
                generator_family = tuple(
                    getattr(
                        self._extractor,
                        "exclusive_generator_family",
                        (),
                    )
                )
                if generator_family:
                    result = self._repository.publish(
                        batch,
                        completed_at=self._clock(),
                        exclusive_generator_family=generator_family,
                    )
                else:
                    result = self._repository.publish(
                        batch,
                        completed_at=self._clock(),
                    )
                writes += result.statement_writes; deactivated += result.deactivated_statements; processed += 1
            except Exception as error:
                self._repository.mark_failed(resource.resource_ref, self._extractor.generator, fingerprint, now=self._clock(), error_code=getattr(error, "code", "extraction_failed"), error_message=str(error))
                failed += 1
        return WorkerResult(len(resources), processed, skipped, failed, writes, deactivated)
