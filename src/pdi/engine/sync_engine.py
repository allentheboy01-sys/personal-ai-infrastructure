import logging
import time

from pdi.adapters.base import Adapter
from pdi.capability.hash import calculate_sha256
from pdi.decision import RequirementType
from pdi.identity import Matcher
from pdi.repository import Repository


logger = logging.getLogger(__name__)


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
                "Matching fact provider=%s "
                "external_id=%s name=%s",
                fact.provider,
                fact.external_id,
                fact.name,
            )

            decision = self.matcher.match(
                fact=fact,
                repository=self.repository,
            )

            if (
                RequirementType.CONTENT_HASH
                in decision.requirements
            ):
                logger.debug(
                    "Content hash required provider=%s "
                    "external_id=%s name=%s",
                    fact.provider,
                    fact.external_id,
                    fact.name,
                )

                content_hash = calculate_sha256(
                    self.adapter.open(fact)
                )

                fact.attributes["content_hash"] = content_hash
                hash_count += 1

                logger.debug(
                    "Content hash calculated provider=%s "
                    "external_id=%s name=%s",
                    fact.provider,
                    fact.external_id,
                    fact.name,
                )

                decision = self.matcher.match(
                    fact=fact,
                    repository=self.repository,
                )

            if decision.requirements:
                logger.error(
                    "Requirements could not be satisfied "
                    "provider=%s external_id=%s requirements=%s",
                    fact.provider,
                    fact.external_id,
                    decision.requirements,
                )

                raise RuntimeError(
                    "SyncEngine could not satisfy requirements: "
                    f"{decision.requirements}"
                )

            self.repository.execute(decision)
            action_count += len(decision.actions)

            logger.debug(
                "Decision executed provider=%s "
                "external_id=%s actions=%d",
                fact.provider,
                fact.external_id,
                len(decision.actions),
            )

        logger.info(
            "Provider scan completed provider=%s facts=%d",
            adapter_name,
            fact_count,
        )

        if scanned_provider is not None:
            active_sources = self.repository.list_active_sources(
                provider=scanned_provider,
            )

            for source in active_sources:
                if source.external_id not in seen_external_ids:
                    missing_count += 1

                    logger.warning(
                        "Source missing from completed scan "
                        "provider=%s external_id=%s "
                        "source_id=%s path=%s",
                        source.provider,
                        source.external_id,
                        source.id,
                        source.path,
                    )

                    decision = self.matcher.deactivate_source(source)
                    self.repository.execute(decision)
                    action_count += len(decision.actions)

                    logger.info(
                        "Source deactivated provider=%s "
                        "external_id=%s source_id=%s path=%s",
                        source.provider,
                        source.external_id,
                        source.id,
                        source.path,
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