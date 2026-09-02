import logging
import time

from pdi.adapters.base import Adapter, ProviderResourceDisappearedError
from pdi.capability.hash import calculate_content_evidence
from pdi.decision import RequirementType
from pdi.identity import Matcher
from pdi.repository import Repository


logger = logging.getLogger(__name__)


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
    ) -> None:
        self.adapter = adapter
        self.matcher = matcher
        self.repository = repository

    def sync_once(self) -> None:
        started_at = time.perf_counter()
        adapter_name = type(self.adapter).__name__

        fact_count = 0
        action_count = 0
        hash_count = 0
        missing_count = 0
        disappeared_count = 0
        authoritative = True

        seen_external_ids: set[str] = set()
        scanned_provider: str | None = None

        logger.info(
            "Sync started provider=%s",
            adapter_name,
        )

        self.adapter.connect()

        logger.info(
            "Provider connected provider=%s",
            adapter_name,
        )

        logger.info(
            "Provider scan started provider=%s",
            adapter_name,
        )

        for fact in self.adapter.scan():
            fact_count += 1

            if scanned_provider is None:
                scanned_provider = fact.provider

            elif fact.provider != scanned_provider:
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
                    authoritative = False
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

        if not authoritative:
            logger.error(
                "Sync incomplete provider=%s disappeared=%d",
                adapter_name,
                disappeared_count,
            )
            raise IncompleteProviderSyncError(
                provider=self.adapter.provider_name,
                disappeared_count=disappeared_count,
            )

        if scanned_provider is not None:
            active_sources = self.repository.list_active_sources(
                provider=scanned_provider,
            )

            for source in active_sources:
                if source.external_id not in seen_external_ids:
                    missing_count += 1

                    logger.warning(
                        "Source missing from completed scan provider=%s",
                        source.provider,
                    )

                    decision = self.matcher.deactivate_source(source)
                    self.repository.execute(decision)
                    action_count += len(decision.actions)

                    logger.info(
                        "Source deactivated provider=%s",
                        source.provider,
                    )

        duration = time.perf_counter() - started_at

        logger.info(
            "Sync completed provider=%s facts=%d "
            "actions=%d hashes=%d missing=%d "
            "duration=%.2fs",
            adapter_name,
            fact_count,
            action_count,
            hash_count,
            missing_count,
            duration,
        )
