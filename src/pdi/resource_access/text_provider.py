from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProviderTextContent:
    status_code: int
    media_type: str | None
    content_length: str | None
    body: AsyncIterator[bytes]
    close: Callable[[], Awaitable[None]]
    content_encoding: str | None = None


class ProviderTextAdapter(Protocol):
    @property
    def provider(self) -> str:
        ...

    async def open_text(
        self,
        provider_locator: str,
    ) -> ProviderTextContent:
        ...
