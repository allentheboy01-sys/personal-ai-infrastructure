from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from .models import ResourceRepresentationKind


@dataclass(frozen=True, slots=True)
class ProviderRepresentation:
    status_code: int
    media_type: str | None
    content_length: str | None
    etag: str | None
    last_modified: str | None
    body: AsyncIterator[bytes]
    close: Callable[[], Awaitable[None]]


class ProviderRepresentationAdapter(Protocol):
    @property
    def provider(self) -> str:
        ...

    async def open_representation(
        self,
        provider_locator: str,
        representation_kind: ResourceRepresentationKind,
    ) -> ProviderRepresentation:
        ...

    async def aclose(self) -> None:
        ...
