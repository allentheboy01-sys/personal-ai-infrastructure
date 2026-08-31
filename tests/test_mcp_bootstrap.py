import pdi_mcp.bootstrap as bootstrap
from pdi.config import ImmichSettings, PDIConfigurationError


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
        "load_nextcloud_settings",
        lambda: (_ for _ in ()).throw(
            PDIConfigurationError("Nextcloud is not configured")
        ),
    )
    monkeypatch.setattr(
        bootstrap,
        "create_runtime_server",
        lambda database_url, immich_settings, nextcloud_settings: (
            calls.update(
                database_url=database_url,
                immich_settings=immich_settings,
                nextcloud_settings=nextcloud_settings,
            )
            or Server()
        ),
    )

    bootstrap.main()

    assert calls == {
        "database_url": "postgresql+psycopg://user:password@db/pdi",
        "immich_settings": None,
        "nextcloud_settings": None,
        "transport": "stdio",
    }


def test_runtime_server_reuses_owned_immich_resource_access_composition(
    monkeypatch,
) -> None:
    calls = {}

    class Engine:
        pass

    class Repository:
        pass

    class Runtime:
        service = object()

        async def aclose(self) -> None:
            calls["closed"] = calls.get("closed", 0) + 1

    runtime = Runtime()
    monkeypatch.setattr(bootstrap, "create_postgres_engine", lambda _url: Engine())
    monkeypatch.setattr(bootstrap, "PostgreSQLRepository", lambda _engine: Repository())
    monkeypatch.setattr(
        bootstrap,
        "create_immich_resource_access_runtime",
        lambda repository, *, base_url, api_key: (
            calls.update(
                repository=repository,
                base_url=base_url,
                api_key=api_key,
            )
            or runtime
        ),
    )
    monkeypatch.setattr(
        bootstrap,
        "create_server",
        lambda *args, **kwargs: (
            calls.update(server_args=args, server_kwargs=kwargs)
            or object()
        ),
    )

    settings = ImmichSettings(
        url="https://provider.example.invalid",
        api_key="IMMICH_TEST_SECRET_SENTINEL",
    )
    bootstrap.create_runtime_server(
        "postgresql+psycopg://test:test@localhost/test",
        immich_settings=settings,
    )

    assert isinstance(calls["repository"], Repository)
    assert calls["base_url"] == settings.url
    assert calls["api_key"] == settings.api_key
    assert calls["server_kwargs"]["resource_access_service"] is runtime.service
    assert calls["server_kwargs"]["resource_access_close"] == runtime.aclose
