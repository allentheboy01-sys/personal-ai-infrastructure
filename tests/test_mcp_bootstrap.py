import pdi_mcp.bootstrap as bootstrap
from pdi.config import PDIConfigurationError


def test_mcp_main_composes_with_database_only(monkeypatch) -> None:
    calls = {}

    class Server:
        def run(self, *, transport) -> None:
            calls["transport"] = transport

    monkeypatch.setattr(
        bootstrap,
        "load_database_url",
        lambda: "postgresql+psycopg://user:password@db/pdi",
    )
    monkeypatch.setattr(
        bootstrap,
        "load_immich_settings",
        lambda: (_ for _ in ()).throw(
            PDIConfigurationError("Immich is not configured")
        ),
    )
    monkeypatch.setattr(
        bootstrap,
        "create_runtime_server",
        lambda database_url, immich_settings: (
            calls.update(
                database_url=database_url,
                immich_settings=immich_settings,
            )
            or Server()
        ),
    )

    bootstrap.main()

    assert calls == {
        "database_url": "postgresql+psycopg://user:password@db/pdi",
        "immich_settings": None,
        "transport": "stdio",
    }
