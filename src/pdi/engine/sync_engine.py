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
        provider = type(self.adapter).__name__

        fact_count = 0
        action_count = 0
        hash_count = 0

        logger.info(
            "Sync started provider=%s",
            provider,
        )

        self.adapter.connect()

        logger.info(
            "Provider connected provider=%s",
            provider,
        )

        logger.info(
            "Provider scan started provider=%s",
            provider,
        )

        for fact in self.adapter.scan():
            fact_count += 1

            logger.debug(
                "Matching fact provider=%s external_id=%s name=%s",
                provider,
                fact.external_id,
                fact.name,
            )

            decision = self.matcher.match(
                fact=fact,
                repository=self.repository,
            )

            if RequirementType.CONTENT_HASH in decision.requirements:
                logger.debug(
                    "Content hash required provider=%s "
                    "external_id=%s name=%s",
                    provider,
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
                    provider,
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
                    provider,
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
                provider,
                fact.external_id,
                len(decision.actions),
            )

        logger.info(
            "Provider scan completed provider=%s facts=%d",
            provider,
            fact_count,
        )

        duration = time.perf_counter() - started_at

        logger.info(
            "Sync completed provider=%s facts=%d actions=%d "
            "hashes=%d duration=%.2fs",
            provider,
            fact_count,
            action_count,
            hash_count,
            duration,
        )