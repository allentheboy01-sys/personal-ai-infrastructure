from dataclasses import replace

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from jarvis.pdi_client.models import ProviderDetail, ProviderSummary, ResourceCapabilities, ResourceDetail, ResourcePage, ResourceSummary
from jarvis.pdi_client.resource_access import ResourceAccessClient

pytestmark = pytest.mark.anyio


class FakePDI:
    def __init__(self):
        self.resource = ResourceSummary("pdi:resource:11111111-1111-4111-8111-111111111111", "file", "Safe title", "image/jpeg", "2026-01-01T00:00:00+00:00", "image", "JPEG", ("Immich",), ResourceCapabilities(True, True, False))
        self.provider = ProviderSummary("immich", "immich", "Immich", "Photos", True, "read_only", 3, "ready", "2026-01-01T00:00:00+00:00")
    async def start(self): pass
    async def close(self): pass
    async def list_resources(self, **kwargs): return ResourcePage((self.resource,), None)
    async def get_resource(self, resource_ref): return ResourceDetail(self.resource, (("Type", "JPEG"),), "image/jpeg", 4)
    async def hydrate_resources(self, refs): return (self.resource,) if refs else ()
    async def list_providers(self): return (self.provider,)
    async def get_provider(self, provider_ref): return ProviderDetail(self.provider, "Read-only photos.", ("Browse image metadata",), (("Available to Jarvis", "completed"),))


async def test_product_api_is_allowlisted_and_private(app_factory):
    async def image(request): return httpx.Response(200, headers={"content-type": "image/jpeg", "content-length": "4"}, content=b"data")
    app = app_factory(pdi_client=FakePDI(), resource_access=ResourceAccessClient(None, transport=httpx.MockTransport(image)))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://jarvis.test") as client:
            resources = await client.get("/api/v1/resources")
            payload = resources.json()
            assert resources.status_code == 200 and resources.headers["cache-control"] == "private, no-store"
            assert set(payload["resources"][0]) == {"resource_ref", "resource_type", "title", "secondary_text", "timestamp", "presentation_kind", "presentation_label", "providers", "capabilities"}
            ref = payload["resources"][0]["resource_ref"]
            detail = await client.get(f"/api/v1/resources/{ref}")
            assert detail.status_code == 200 and "checksum" not in detail.text and "location" not in detail.text
            providers = await client.get("/api/v1/providers")
            assert providers.status_code == 200 and "pipeline" not in providers.text
            provider = await client.get("/api/v1/providers/immich")
            assert provider.status_code == 200 and provider.json()["summary"]["operational_state"] == "ready"
            representation = await client.get(f"/api/v1/resources/{ref}/representation?kind=thumbnail")
            assert representation.status_code == 200 and representation.content == b"data"


async def test_live_mode_never_returns_synthetic_product_data(app_factory):
    app = app_factory()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://jarvis.test") as client:
            assert (await client.get("/api/v1/resources")).status_code == 503
            assert (await client.get("/api/v1/providers")).status_code == 503
