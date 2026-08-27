from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from jarvis.pdi_client.mcp import MCPPDIClient
from jarvis.pdi_client.resource_access import ResourceAccessClient
from jarvis.runtime.hermes_adapter import HermesRuntimeAdapter
from jarvis.state import Base
from jarvis.web import production


def _settings(tmp_path: Path, **updates) -> production.ProductionSettings:
    static = tmp_path / "static"
    static.mkdir(exist_ok=True)
    (static / "index.html").write_text("<!doctype html>", encoding="utf-8")
    values = {
        "database_url": "postgresql+psycopg://jarvis_app:secret@127.0.0.1:5433/jarvis",
        "allowed_tailscale_login": "allowed@example.test",
        "allowed_origin": "https://jarvis.test",
        "static_dir": static,
        "hermes_bridge_command": "/release/bin/hermes-bridge",
        "pdi_mcp_command": "/opt/pdi/deployment/mcp/pdi-mcp",
        "resource_access_socket": "/run/pdi/resource-access.sock",
    }
    return production.ProductionSettings(**(values | updates))


def test_production_configuration_fails_closed(monkeypatch, tmp_path: Path) -> None:
    for name in tuple(production.ProductionSettings.model_fields):
        monkeypatch.delenv(f"JARVIS_{name.upper()}", raising=False)
    with pytest.raises(ValidationError):
        production.ProductionSettings()
    with pytest.raises(ValidationError):
        _settings(tmp_path, bind_host="0.0.0.0")
    with pytest.raises(ValidationError):
        _settings(tmp_path, allowed_origin="http://jarvis.test")
    with pytest.raises(ValidationError):
        _settings(tmp_path, hermes_bridge_command="relative-launcher")


def test_production_composes_only_real_boundaries(monkeypatch, tmp_path: Path) -> None:
    captured = {}
    monkeypatch.setattr(production, "create_jarvis_engine", lambda url: ("engine", url))
    monkeypatch.setattr(production, "create_app", lambda **kwargs: captured.update(kwargs) or "application")
    result = production.create_production_app(_settings(tmp_path))
    assert result == "application"
    assert captured["engine"][1].endswith("/jarvis")
    assert isinstance(captured["runtime"], HermesRuntimeAdapter)
    assert isinstance(captured["pdi_client"], MCPPDIClient)
    assert isinstance(captured["resource_access"], ResourceAccessClient)
    assert type(captured["auth_adapter"]).__name__ == "TailscaleServeAuth"
    assert "Mock" not in repr(captured)


def test_production_settings_hide_secrets(tmp_path: Path) -> None:
    rendered = repr(_settings(tmp_path))
    assert "secret" not in rendered
    assert "allowed@example.test" not in rendered


@pytest.mark.anyio
async def test_production_graph_starts_with_injected_external_fakes(monkeypatch, tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    class RuntimeBoundary:
        def __init__(self, config): self.config = config
        async def start_turn(self, context): raise AssertionError("not used")
        async def stream_events(self, turn_id):
            if False: yield None
        async def cancel_turn(self, turn_id): return None

    class PDIBoundary:
        def __init__(self, config): self.started = False
        async def start(self): self.started = True
        async def close(self): self.started = False

    monkeypatch.setattr(production, "create_jarvis_engine", lambda url: engine)
    monkeypatch.setattr(production, "HermesRuntimeAdapter", RuntimeBoundary)
    monkeypatch.setattr(production, "MCPPDIClient", PDIBoundary)
    app = production.create_production_app(_settings(tmp_path))
    async with app.router.lifespan_context(app):
        assert app.state.jarvis_state is not None
