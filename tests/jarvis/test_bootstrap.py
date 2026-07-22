from types import SimpleNamespace
from uuid import uuid4

import jarvis.bootstrap as bootstrap
from jarvis import ToolCall


class StubQueryService:
    def list_assets(self):
        return ()

    def get_asset(self, asset_id: str):
        return None


def test_bootstrap_builds_application_with_registered_tools(
    monkeypatch,
) -> None:
    engine = object()
    repository = object()
    query_service = StubQueryService()
    observed_urls: list[str] = []
    observed_engines: list[object] = []
    observed_repositories: list[object] = []

    def create_engine(database_url: str):
        observed_urls.append(database_url)
        return engine

    def create_repository(received_engine):
        observed_engines.append(received_engine)
        return repository

    def create_query_service(received_repository):
        observed_repositories.append(received_repository)
        return query_service

    monkeypatch.setattr(
        bootstrap,
        "create_postgres_engine",
        create_engine,
    )
    monkeypatch.setattr(
        bootstrap,
        "PostgreSQLRepository",
        create_repository,
    )
    monkeypatch.setattr(
        bootstrap,
        "QueryService",
        create_query_service,
    )
    settings = SimpleNamespace(
        database=SimpleNamespace(url="postgresql://test"),
    )

    application = bootstrap.create_jarvis_application(settings)

    list_result = application.execute(
        ToolCall(name="list_assets", arguments={})
    )
    get_result = application.execute(
        ToolCall(
            name="get_asset",
            arguments={"asset_id": str(uuid4())},
        )
    )

    assert list_result.success is True
    assert list_result.data == ()
    assert get_result.success is False
    assert get_result.error is not None
    assert get_result.error.code == "asset_not_found"
    assert observed_urls == ["postgresql://test"]
    assert observed_engines == [engine]
    assert observed_repositories == [repository]
