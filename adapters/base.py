from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable


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