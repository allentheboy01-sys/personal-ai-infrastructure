from starlette.applications import Starlette

from pdi.config import ImmichSettings, load_immich_settings
from pdi.config.settings import load_database_url
from pdi.database import create_postgres_engine
from pdi.repository import PostgreSQLRepository
from pdi.resource_access import (
    ImmichRepresentationAdapter,
    ResourceAccessService,
)

from .app import create_app


def create_runtime_app(
    *,
    database_url: str | None = None,
    immich_settings: ImmichSettings | None = None,
) -> Starlette:
    engine = create_postgres_engine(database_url or load_database_url())
    settings = immich_settings or load_immich_settings()
    adapter = ImmichRepresentationAdapter(
        settings.url,
        settings.api_key,
    )
    repository = PostgreSQLRepository(engine)
    service = ResourceAccessService(
        repository,
        {adapter.provider: adapter},
    )

    async def shutdown() -> None:
        await adapter.aclose()
        engine.dispose()

    return create_app(service, shutdown=shutdown)
