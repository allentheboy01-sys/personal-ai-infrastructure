from dataclasses import dataclass, field

from .immich import ImmichRepresentationAdapter
from .repository import ResourceAccessRepository
from .service import ResourceAccessService


@dataclass(slots=True)
class ImmichResourceAccessRuntime:
    """Owned Immich Resource Access composition with idempotent shutdown."""

    service: ResourceAccessService
    _adapter: ImmichRepresentationAdapter
    _closed: bool = field(default=False, init=False)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._adapter.aclose()


def create_immich_resource_access_runtime(
    repository: ResourceAccessRepository,
    *,
    base_url: str,
    api_key: str,
) -> ImmichResourceAccessRuntime:
    """Compose the official bounded Immich Resource Access runtime."""

    adapter = ImmichRepresentationAdapter(base_url, api_key)
    return ImmichResourceAccessRuntime(
        service=ResourceAccessService(
            repository,
            {adapter.provider: adapter},
        ),
        _adapter=adapter,
    )
