from datetime import UTC, datetime

import pytest

from pdi.adapters.immich import (
    IMMICH_INCREMENTAL_MECHANISM,
    ImmichBootstrapRequiredError,
    ImmichIncrementalSync,
    decode_immich_checkpoint,
    encode_immich_checkpoint,
)
from pdi.engine import InvalidCheckpointError, ReconciliationRequiredError
from pdi.sync_state import ProviderSyncState


def _state(
    checkpoint: str | None,
    *,
    version: int = 0,
    reconciliation_required: bool = False,
) -> ProviderSyncState:
    now = datetime(2026, 9, 3, tzinfo=UTC)
    return ProviderSyncState(
        provider="immich",
        mechanism=IMMICH_INCREMENTAL_MECHANISM,
        checkpoint=checkpoint,
        version=version,
        reconciliation_required=reconciliation_required,
        created_at=now,
        updated_at=now,
    )


class _StateRepository:
    def __init__(self, state: ProviderSyncState) -> None:
        self.state = state

    def get_or_create(self, provider, mechanism):
        return self.state

    def read(self, provider, mechanism):
        return self.state

    def compare_and_swap_checkpoint(
        self, provider, mechanism, *, expected_version, checkpoint
    ):
        if self.state.version != expected_version:
            return None
        self.state = _state(checkpoint, version=expected_version + 1)
        return self.state

    def mark_reconciliation_required(
        self, provider, mechanism, *, expected_version
    ):
        if self.state.version != expected_version:
            return None
        self.state = _state(
            self.state.checkpoint,
            version=expected_version + 1,
            reconciliation_required=True,
        )
        return self.state

    def recover_after_reconciliation(
        self,
        provider,
        mechanism,
        *,
        expected_version,
        trusted_checkpoint,
    ):
        if (
            self.state.version != expected_version
            or not self.state.reconciliation_required
        ):
            return None
        self.state = _state(
            trusted_checkpoint,
            version=expected_version + 1,
        )
        return self.state


class _Adapter:
    provider_name = "immich"

    def __init__(self) -> None:
        self.windows: list[tuple[str, str]] = []

    def scan_updated_window(self, *, updated_after, updated_before):
        self.windows.append((updated_after, updated_before))
        return ()


class _Engine:
    def __init__(self, repository: _StateRepository) -> None:
        self.repository = repository
        self.full_calls = 0
        self.incremental_calls = 0
        self.full_error: Exception | None = None

    def sync_incremental(self, mechanism, discover):
        self.incremental_calls += 1
        batch = discover(self.repository.state)
        tuple(batch.facts)
        return self.repository.compare_and_swap_checkpoint(
            "immich",
            mechanism,
            expected_version=self.repository.state.version,
            checkpoint=batch.next_checkpoint,
        )

    def sync_once(self):
        self.full_calls += 1
        if self.full_error is not None:
            raise self.full_error


def test_checkpoint_codec_normalizes_utc_deterministically() -> None:
    parsed = decode_immich_checkpoint("2026-09-03T09:23:45.123456+08:00")
    assert parsed == datetime(2026, 9, 3, 1, 23, 45, 123456, tzinfo=UTC)
    assert encode_immich_checkpoint(parsed) == "2026-09-03T01:23:45.123456Z"
    assert decode_immich_checkpoint(
        "2026-09-02T20:23:45.123456-05:00"
    ) == parsed


@pytest.mark.parametrize("value", ["", "invalid", "2026-09-03T01:23:45"])
def test_checkpoint_decoder_rejects_invalid_or_naive_values(value) -> None:
    with pytest.raises(InvalidCheckpointError):
        decode_immich_checkpoint(value)


def test_incremental_window_uses_overlap_and_never_regresses_checkpoint() -> None:
    repository = _StateRepository(
        _state("2026-09-03T01:00:00.000000Z", version=4)
    )
    adapter = _Adapter()
    engine = _Engine(repository)
    service = ImmichIncrementalSync(
        adapter, engine, repository,
        clock=lambda: datetime(2026, 9, 3, 0, 50, tzinfo=UTC),
    )

    result = service.run_incremental()

    assert adapter.windows == [(
        "2026-09-03T00:55:00.000000Z",
        "2026-09-03T01:00:00.000000Z",
    )]
    assert result.checkpoint == "2026-09-03T01:00:00.000000Z"


def test_uninitialized_and_reconciliation_states_require_explicit_flows() -> None:
    adapter = _Adapter()
    uninitialized = _StateRepository(_state(None))
    with pytest.raises(ImmichBootstrapRequiredError):
        ImmichIncrementalSync(
            adapter, _Engine(uninitialized), uninitialized
        ).run_incremental()
    assert uninitialized.state.checkpoint is None
    assert uninitialized.state.version == 0
    assert uninitialized.state.reconciliation_required is False

    required = _StateRepository(
        _state("old", reconciliation_required=True)
    )
    with pytest.raises(ReconciliationRequiredError):
        ImmichIncrementalSync(adapter, _Engine(required), required).run_incremental()


def test_bootstrap_rejects_initialized_state_without_running_full() -> None:
    repository = _StateRepository(
        _state("2026-09-03T01:00:00.000000Z", version=2)
    )
    engine = _Engine(repository)

    with pytest.raises(RuntimeError, match="uninitialized state"):
        ImmichIncrementalSync(_Adapter(), engine, repository).bootstrap()

    assert engine.full_calls == 0
    assert repository.state.checkpoint == "2026-09-03T01:00:00.000000Z"
    assert repository.state.version == 2


def test_bootstrap_cannot_bypass_reconciliation_latch() -> None:
    repository = _StateRepository(
        _state(None, version=2, reconciliation_required=True)
    )
    engine = _Engine(repository)

    with pytest.raises(RuntimeError, match="uninitialized state"):
        ImmichIncrementalSync(_Adapter(), engine, repository).bootstrap()

    assert engine.full_calls == 0
    assert repository.state.checkpoint is None
    assert repository.state.version == 2
    assert repository.state.reconciliation_required is True


def test_bootstrap_captures_anchor_before_full_and_commits_last() -> None:
    repository = _StateRepository(_state(None))
    engine = _Engine(repository)
    observed: list[str] = []

    def clock():
        observed.append("anchor")
        return datetime(2026, 9, 3, 1, 0, tzinfo=UTC)

    original_sync = engine.sync_once

    def full():
        assert observed == ["anchor"]
        assert repository.state.checkpoint is None
        original_sync()

    engine.sync_once = full
    result = ImmichIncrementalSync(
        _Adapter(), engine, repository, clock=clock
    ).bootstrap()

    assert result.checkpoint == "2026-09-03T01:00:00.000000Z"
    assert engine.full_calls == 1


def test_failed_bootstrap_does_not_initialize_checkpoint() -> None:
    repository = _StateRepository(_state(None))
    engine = _Engine(repository)
    engine.full_error = RuntimeError("full failed")
    service = ImmichIncrementalSync(
        _Adapter(), engine, repository,
        clock=lambda: datetime(2026, 9, 3, 1, 0, tzinfo=UTC),
    )

    with pytest.raises(RuntimeError, match="full failed"):
        service.bootstrap()
    assert repository.state.checkpoint is None
    assert repository.state.version == 0


def test_explicit_recovery_commits_anchor_only_after_successful_full() -> None:
    repository = _StateRepository(
        _state("old", version=3, reconciliation_required=True)
    )
    engine = _Engine(repository)
    service = ImmichIncrementalSync(
        _Adapter(), engine, repository,
        clock=lambda: datetime(2026, 9, 3, 2, 0, tzinfo=UTC),
    )

    recovered = service.recover()

    assert recovered.checkpoint == "2026-09-03T02:00:00.000000Z"
    assert recovered.version == 4
    assert recovered.reconciliation_required is False


def test_failed_recovery_keeps_reconciliation_required() -> None:
    repository = _StateRepository(
        _state("old", version=3, reconciliation_required=True)
    )
    engine = _Engine(repository)
    engine.full_error = RuntimeError("full failed")
    service = ImmichIncrementalSync(
        _Adapter(), engine, repository,
        clock=lambda: datetime(2026, 9, 3, 2, 0, tzinfo=UTC),
    )

    with pytest.raises(RuntimeError, match="full failed"):
        service.recover()
    assert repository.state.checkpoint == "old"
    assert repository.state.version == 3
    assert repository.state.reconciliation_required is True
