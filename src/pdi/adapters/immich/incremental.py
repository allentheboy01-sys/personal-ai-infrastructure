from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pdi.engine import (
    CheckpointCASConflictError,
    DiscoveryBatch,
    DiscoveryMode,
    InvalidCheckpointError,
    ReconciliationRequiredError,
    SyncEngine,
)
from pdi.sync_state import ProviderSyncState, ProviderSyncStateRepository

from .adapter import ImmichAdapter


IMMICH_INCREMENTAL_MECHANISM = "metadata_updated_at_v1"
IMMICH_INCREMENTAL_OVERLAP = timedelta(minutes=5)


class ImmichBootstrapRequiredError(RuntimeError):
    """No trusted Immich incremental checkpoint has been established."""


def encode_immich_checkpoint(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidCheckpointError("Immich checkpoint must be timezone-aware")
    normalized = value.astimezone(UTC)
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def decode_immich_checkpoint(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise InvalidCheckpointError("Immich checkpoint must be non-empty")
    try:
        serialized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(serialized)
    except ValueError as error:
        raise InvalidCheckpointError("Malformed Immich checkpoint") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InvalidCheckpointError("Immich checkpoint must be timezone-aware")
    return parsed.astimezone(UTC)


@dataclass(slots=True)
class ImmichIncrementalSync:
    adapter: ImmichAdapter
    engine: SyncEngine
    state_repository: ProviderSyncStateRepository
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def run_incremental(self) -> ProviderSyncState:
        state = self.state_repository.get_or_create(
            self.adapter.provider_name,
            IMMICH_INCREMENTAL_MECHANISM,
        )
        if state.reconciliation_required:
            raise ReconciliationRequiredError(
                "Immich incremental state requires explicit recovery"
            )
        if state.checkpoint is None:
            raise ImmichBootstrapRequiredError(
                "Immich incremental sync requires an explicit full bootstrap"
            )

        def discover(current: ProviderSyncState) -> DiscoveryBatch:
            previous = decode_immich_checkpoint(current.checkpoint or "")
            now = self._utc_now()
            window_end = max(now, previous)
            window_start = previous - IMMICH_INCREMENTAL_OVERLAP
            return DiscoveryBatch(
                provider=self.adapter.provider_name,
                mode=DiscoveryMode.INCREMENTAL_NON_AUTHORITATIVE,
                facts=self.adapter.scan_updated_window(
                    updated_after=encode_immich_checkpoint(window_start),
                    updated_before=encode_immich_checkpoint(window_end),
                ),
                next_checkpoint=encode_immich_checkpoint(window_end),
            )

        return self.engine.sync_incremental(
            IMMICH_INCREMENTAL_MECHANISM,
            discover,
        )

    def bootstrap(self) -> ProviderSyncState:
        state = self.state_repository.get_or_create(
            self.adapter.provider_name,
            IMMICH_INCREMENTAL_MECHANISM,
        )
        if state.reconciliation_required or state.checkpoint is not None:
            raise RuntimeError("Immich bootstrap requires uninitialized state")
        anchor = encode_immich_checkpoint(self._utc_now())
        self.engine.sync_once()
        advanced = self.state_repository.compare_and_swap_checkpoint(
            state.provider,
            state.mechanism,
            expected_version=state.version,
            checkpoint=anchor,
        )
        if advanced is None:
            raise CheckpointCASConflictError("Immich bootstrap checkpoint CAS failed")
        return advanced

    def recover(self) -> ProviderSyncState:
        state = self.state_repository.get_or_create(
            self.adapter.provider_name,
            IMMICH_INCREMENTAL_MECHANISM,
        )
        if not state.reconciliation_required:
            raise RuntimeError("Immich recovery requires reconciliation state")
        anchor = encode_immich_checkpoint(self._utc_now())
        self.engine.sync_once()
        recovered = self.state_repository.recover_after_reconciliation(
            state.provider,
            state.mechanism,
            expected_version=state.version,
            trusted_checkpoint=anchor,
        )
        if recovered is None:
            raise CheckpointCASConflictError("Immich recovery checkpoint CAS failed")
        return recovered

    def _utc_now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise InvalidCheckpointError("Immich sync clock must be timezone-aware")
        return value.astimezone(UTC)
