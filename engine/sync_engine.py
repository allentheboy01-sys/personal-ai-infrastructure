from adapters.base import Adapter
from capability.hash import calculate_sha256
from decision import RequirementType
from identity import Matcher
from repository import Repository


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
        self.adapter.connect()

        for fact in self.adapter.scan():
            decision = self.matcher.match(
                fact=fact,
                repository=self.repository,
            )

            if RequirementType.CONTENT_HASH in decision.requirements:
                content_hash = calculate_sha256(
                    self.adapter.open(fact)
                )

                fact.attributes["content_hash"] = content_hash

                decision = self.matcher.match(
                    fact=fact,
                    repository=self.repository,
                )

            if decision.requirements:
                raise RuntimeError(
                    "SyncEngine could not satisfy requirements: "
                    f"{decision.requirements}"
                )

            self.repository.execute(decision)