from typing import Protocol

from .models import ProviderRetrievalHit


class ProviderRetrievalAdapter(Protocol):
    """Provider-native retrieval without PDI persistence access."""

    @property
    def provider(self) -> str:
        ...

    def search_resources(
        self,
        *,
        query: str,
        limit: int,
    ) -> tuple[ProviderRetrievalHit, ...]:
        ...
