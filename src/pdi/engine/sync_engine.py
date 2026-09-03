import logging
import time
from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum

from pdi.adapters.base import (
    Adapter,
    ProviderFact,
    ProviderResourceDisappearedError,
)
from pdi.capability.hash import calculate_content_evidence
from pdi.decision import RequirementType
from pdi.identity import Matcher
from pdi.repository import Repository
from pdi.sync_state import (
    ProviderSyncState,
    ProviderSyncStateRepository,
)


logger = logging.getLogger(__name__)


class DiscoveryMode(StrEnum):
    FULL_AUTHORITATIVE = "full_authoritative"
    INCREMENTAL_NON_AUTHORITATIVE = "incremental_non_authoritative"


@dataclass(frozen=True, slots=True)
class QualifiedTombstone:
    """Explicit deletion evidence accepted by a future Provider mechanism."""

    provider: str
    external_id: str


@dataclass(frozen=True, slots=True)
class DiscoveryBatch:
    """Run-level discovery mechanics kept separate from ProviderFact."""

    provider: str
    mode: DiscoveryMode
    facts: Iterable[ProviderFact]
    next_checkpoint: str | None = None
    qualified_tombstones: tuple[QualifiedTombstone, ...] = ()


class InvalidCheckpointError(RuntimeError):
    """A discovery mechanism cannot safely interpret its current state."""


class MissingNextCheckpointError(RuntimeError):
    """Incremental discovery did not produce a trusted next checkpoint."""


class ReconciliationRequiredError(RuntimeError):
    """Incremental discovery is blocked pending a full reconciliation."""


class CheckpointCASConflictError(RuntimeError):
    """Another writer advanced the Provider checkpoint first."""


class IncompleteProviderSyncError(RuntimeError):
    """A provider traversal completed but was not authoritative."""

    def __init__(self, provider: str, disappeared_count: int) -> None:
        self.provider = provider
        self.disappeared_count = disappeared_count
        super().__init__(
            "Provider sync incomplete: "
            f"provider={provider} disappeared={disappeared_count}"
        )


class SyncEngine:
    def __init__(
        self,
        adapter: Adapter,
        matcher: Matcher,
        repository: Repository,
        sync_state_repository: ProviderSyncStateRepository | None = None,
    ) -> None:
        self.adapter = adapter
        self.matcher = matcher
        self.repository = repository
        self.sync_state_repository = sync_state_repository

    def sync_once(self) -> None:
        """Run the existing complete, authoritative Provider inventory."""

        self.adapter.connect()
        self._run_batch(
            DiscoveryBatch(
                provider=self.adapter.provider_name,
                mode=DiscoveryMode.FULL_AUTHORITATIVE,
                facts=self.adapter.scan(),
            )
        )

    def sync_incremental(
        self,
        mechanism: str,
        discover: Callable[[ProviderSyncState], DiscoveryBatch],
    ) -> ProviderSyncState:
        """Apply one replay-safe incremental batch and CAS its checkpoint last."""

        if self.sync_state_repository is None:
            raise RuntimeError(
                "Incremental sync requires Provider sync state persistence"
            )
        state = self.sync_state_repository.get_or_create(
            self.adapter.provider_name,
            mechanism,
        )
        if state.reconciliation_required:
            raise ReconciliationRequiredError(
                "Provider incremental state requires full reconciliation"
            )

        self.adapter.connect()
        try:
            batch = discover(state)
        except InvalidCheckpointError:
            self._mark_reconciliation_required(state)
            raise

        if batch.mode is not DiscoveryMode.INCREMENTAL_NON_AUTHORITATIVE:
            raise ValueError(
                "Incremental discovery must return a non-authoritative batch"
            )
        if batch.provider != state.provider:
            raise ValueError("Discovery batch Provider does not match state")
        if not isinstance(batch.next_checkpoint, str) or not batch.next_checkpoint:
            raise MissingNextCheckpointError(
                "Incremental discovery requires a non-empty next checkpoint"
            )

        try:
            self._run_batch(batch)
        except InvalidCheckpointError:
            self._mark_reconciliation_required(state)
            raise
        advanced = self.sync_state_repository.compare_and_swap_checkpoint(
            state.provider,
            state.mechanism,
            expected_version=state.version,
            checkpoint=batch.next_checkpoint,
        )
        if advanced is None:
            raise CheckpointCASConflictError(
                "Provider checkpoint compare-and-swap failed"
            )
        return advanced

    def _mark_reconciliation_required(
        self,
        state: ProviderSyncState,
    ) -> None:
        if self.sync_state_repository is None:
            raise RuntimeError("Provider sync state persistence is unavailable")
        marked = self.sync_state_repository.mark_reconciliation_required(
            state.provider,
            state.mechanism,
            expected_version=state.version,
        )
        if marked is None:
            raise CheckpointCASConflictError(
                "Provider checkpoint changed while marking reconciliation"
            ) from None

    def _run_batch(self, batch: DiscoveryBatch) -> None:
        started_at = time.perf_counter()
        adapter_name = type(self.adapter).__name__

        fact_count = 0
        action_count = 0
        hash_count = 0
        missing_count = 0
        disappeared_count = 0
        reconciliation_safe = True

        seen_external_ids: set[str] = set()
        scanned_provider = batch.provider

        logger.info(
            "Sync started provider=%s",
            adapter_name,
        )

        logger.info(
            "Provider scan started provider=%s mode=%s",
            adapter_name,
            batch.mode.value,
        )

        for fact in batch.facts:
            fact_count += 1

            if fact.provider != scanned_provider:
                raise RuntimeError(
                    "A single sync run cannot contain multiple providers: "
                    f"{scanned_provider}, {fact.provider}"
                )

            if fact.external_id is not None:
                seen_external_ids.add(fact.external_id)

            logger.debug(
                "Matching fact provider=%s kind=%s",
                fact.provider,
                fact.kind,
            )

            decision = self.matcher.match(
                fact=fact,
                repository=self.repository,
            )

            content_requirements = {
                RequirementType.CONTENT_HASH,
                RequirementType.CONTENT_EVIDENCE,
            }
            evidence_was_computed = False
            if content_requirements.intersection(decision.requirements):
                logger.debug(
                    "Content evidence required provider=%s kind=%s",
                    fact.provider,
                    fact.kind,
                )

                try:
                    content_evidence = calculate_content_evidence(
                        self.adapter.open(fact)
                    )
                except ProviderResourceDisappearedError:
                    reconciliation_safe = False
                    disappeared_count += 1
                    logger.warning(
                        "Provider resource disappeared during content read "
                        "provider=%s",
                        fact.provider,
                    )
                    continue

                fact.attributes["content_hash"] = content_evidence.sha256
                fact.attributes["content_byte_length"] = (
                    content_evidence.byte_length
                )
                if fact.kind == "message":
                    fact.attributes["version_tag"] = content_evidence.sha256
                hash_count += 1
                evidence_was_computed = True

                logger.debug(
                    "Content evidence calculated provider=%s kind=%s",
                    fact.provider,
                    fact.kind,
                )

                decision = self.matcher.match(
                    fact=fact,
                    repository=self.repository,
                )

            if decision.requirements:
                logger.error(
                    "Requirements could not be satisfied "
                    "provider=%s kind=%s requirements=%s",
                    fact.provider,
                    fact.kind,
                    decision.requirements,
                )

                if (
                    evidence_was_computed
                    and content_requirements.intersection(
                        decision.requirements
                    )
                ):
                    raise RuntimeError(
                        "Content evidence requirement remained after "
                        "one Provider body read"
                    )

                raise RuntimeError(
                    "SyncEngine could not satisfy requirements: "
                    f"{decision.requirements}"
                )

            self.repository.execute(decision)
            action_count += len(decision.actions)

            logger.debug(
                "Decision executed provider=%s kind=%s actions=%d",
                fact.provider,
                fact.kind,
                len(decision.actions),
            )

        logger.info(
            "Provider scan completed provider=%s facts=%d",
            adapter_name,
            fact_count,
        )

        if not reconciliation_safe:
            logger.error(
                "Sync incomplete provider=%s disappeared=%d",
                adapter_name,
                disappeared_count,
            )
            raise IncompleteProviderSyncError(
                provider=self.adapter.provider_name,
                disappeared_count=disappeared_count,
            )

        tombstone_decisions = []
        for tombstone in batch.qualified_tombstones:
            if tombstone.provider != scanned_provider:
                raise ValueError(
                    "Qualified tombstone Provider does not match discovery"
                )
            source = self.repository.find_source(
                tombstone.provider,
                tombstone.external_id,
            )
            if source is not None and source.is_active:
                decision = self.matcher.deactivate_source(deepcopy(source))
                tombstone_decisions.append(decision)
                action_count += len(decision.actions)
        self.repository.execute_many(tuple(tombstone_decisions))

        if batch.mode is DiscoveryMode.FULL_AUTHORITATIVE:
            active_sources = self.repository.list_active_sources(
                provider=scanned_provider,
            )

            missing_decisions = []
            for source in active_sources:
                if source.external_id not in seen_external_ids:
                    missing_count += 1

                    logger.warning(
                        "Source missing from completed scan provider=%s",
                        source.provider,
                    )

                    decision = self.matcher.deactivate_source(deepcopy(source))
                    missing_decisions.append(decision)
                    action_count += len(decision.actions)

                    logger.info(
                        "Source deactivated provider=%s",
                        source.provider,
                    )
            self.repository.execute_many(tuple(missing_decisions))

        duration = time.perf_counter() - started_at

        logger.info(
            "Sync completed provider=%s facts=%d "
            "actions=%d hashes=%d missing=%d mode=%s "
            "duration=%.2fs",
            adapter_name,
            fact_count,
            action_count,
            hash_count,
            missing_count,
            batch.mode.value,
            duration,
        )
