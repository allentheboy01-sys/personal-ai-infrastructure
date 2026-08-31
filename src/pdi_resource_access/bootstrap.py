from starlette.applications import Starlette

from pdi.config import ImmichSettings, load_immich_settings
from pdi.config.settings import load_database_url
from pdi.database import create_postgres_engine
from pdi.repository import PostgreSQLRepository
from pdi.resource_access import (
    create_immich_resource_access_runtime,
)

from .app import create_app


def create_runtime_app(
    *,
    database_url: str | None = None,
    immich_settings: ImmichSettings | None = None,
) -> Starlette:
    engine = create_postgres_engine(database_url or load_database_url())
    settings = immich_settings or load_immich_settings()
    repository = PostgreSQLRepository(engine)
    runtime = create_immich_resource_access_runtime(
        repository,
        base_url=settings.url,
        api_key=settings.api_key,
    )

    async def shutdown() -> None:
        await runtime.aclose()
        engine.dispose()

    return create_app(runtime.service, shutdown=shutdown)
