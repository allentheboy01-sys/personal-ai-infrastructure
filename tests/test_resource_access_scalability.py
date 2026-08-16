import asyncio
from uuid import uuid4

from pdi.query import format_resource_ref
from pdi.resource_access import (
    ProviderRepresentation,
    ResourceAccessService,
    ResourceAccessSource,
)


class ManifestRepository:
    def __init__(self, mappings) -> None:
        self.mappings = mappings
        self.calls = 0

    def resolve_access_sources(self, asset_id: str):
        self.calls += 1
        return self.mappings.get(asset_id)


class CountingAdapter:
    provider = "immich"

    def __init__(self) -> None:
        self.calls = 0
        self.active = 0
        self.peak_active = 0

    async def open_representation(self, locator, kind):
        del locator, kind
        self.calls += 1
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)

        async def body():
            await asyncio.sleep(0.001)
            yield b"thumbnail"

        closed = False

        async def close():
            nonlocal closed
            if not closed:
                closed = True
                self.active -= 1

        return ProviderRepresentation(
            200,
            "image/webp",
            "9",
            None,
            None,
            body(),
            close,
        )

    async def aclose(self):
        return None


def _source(asset_id: str) -> ResourceAccessSource:
    return ResourceAccessSource(
        provider="immich",
        provider_locator=asset_id,
        resource_type="file",
        mime_type="image/jpeg",
    )


async def _fetch(service, resource_ref: str) -> int:
    opened = await service.open_representation(resource_ref, "thumbnail")
    total = 0
    async for chunk in opened:
        total += len(chunk)
    return total


def test_100_requests_are_bounded_to_eight_active_streams() -> None:
    asset_ids = [str(uuid4()) for _ in range(100)]
    repository = ManifestRepository({
        asset_id: (_source(asset_id),) for asset_id in asset_ids
    })
    adapter = CountingAdapter()
    service = ResourceAccessService(
        repository,
        {adapter.provider: adapter},
        max_active_streams=8,
    )

    async def run() -> None:
        sizes = await asyncio.gather(*[
            _fetch(service, format_resource_ref(asset_id))
            for asset_id in asset_ids
        ])
        assert sizes == [9] * 100

    asyncio.run(run())
    assert repository.calls == 100
    assert adapter.calls == 100
    assert adapter.peak_active == 8
    assert adapter.active == 0


def test_500_resource_manifest_does_not_prefetch_binary_data() -> None:
    asset_ids = [str(uuid4()) for _ in range(500)]
    resource_refs = tuple(format_resource_ref(item) for item in asset_ids)
    repository = ManifestRepository({
        asset_id: (_source(asset_id),) for asset_id in asset_ids
    })
    adapter = CountingAdapter()
    service = ResourceAccessService(
        repository,
        {adapter.provider: adapter},
    )

    assert len(resource_refs) == 500
    assert repository.calls == 0
    assert adapter.calls == 0

    async def run() -> None:
        sizes = await asyncio.gather(*[
            _fetch(service, resource_ref)
            for resource_ref in resource_refs[:16]
        ])
        assert sizes == [9] * 16

    asyncio.run(run())
    assert repository.calls == 16
    assert adapter.calls == 16
    assert adapter.peak_active == 8
