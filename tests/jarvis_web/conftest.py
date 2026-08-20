from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from jarvis.state import Base
from jarvis.runtime import MockRuntimeAdapter
from jarvis.web import JarvisWebSettings, TestAuthAdapter, create_app
from jarvis.pdi_client import ResourceAccessClient


ORIGIN = "https://jarvis.test"
WRITE_HEADERS = {"Origin": ORIGIN, "X-Jarvis-Request": "web-v1", "Content-Type": "application/json"}


@pytest.fixture
def app_factory(tmp_path: Path):
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>Jarvis</title>", encoding="utf-8")
    (static / "app.js").write_text("console.log('synthetic')", encoding="utf-8")
    (static / "assets").mkdir()
    (static / "assets/app-ABC123.js").write_text("console.log('hashed')", encoding="utf-8")
    def build(runtime: MockRuntimeAdapter | None = None, *, pdi_client=None, resource_access: ResourceAccessClient | None = None):
        engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        return create_app(engine=engine, settings=JarvisWebSettings(allowed_origin=ORIGIN, static_dir=static), auth_adapter=TestAuthAdapter(), runtime=runtime or MockRuntimeAdapter(), pdi_client=pdi_client, resource_access=resource_access)
    return build


@pytest.fixture
def app(app_factory):
    return app_factory()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(app):
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://jarvis.test") as test_client:
            yield test_client
