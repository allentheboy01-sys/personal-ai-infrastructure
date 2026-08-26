from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable


class ProviderResourceDisappearedError(RuntimeError):
    """An observed provider object disappeared before its content was read."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(
            "Provider resource disappeared during content read: "
            f"provider={provider}"
        )


@dataclass
class ProviderFact:
    provider: str
    kind: str
    external_id: str | None
    name: str | None
    attributes: dict[str, Any]
    raw: dict[str, Any]


class Adapter(ABC):
    provider_name: str

    @abstractmethod
    def connect(self) -> None:
        """Connect to the provider and verify credentials."""
        pass

    @abstractmethod
    def scan(self) -> Iterable[ProviderFact]:
        """Read facts from the provider."""
        pass

    @abstractmethod
    def open(
        self,
        fact: ProviderFact,
    ) -> Iterable[bytes]:
        """Read a provider object's content as byte chunks."""
        raise NotImplementedError
