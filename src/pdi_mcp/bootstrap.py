from mcp.server import MCPServer

from pdi.config.settings import (
    ImmichSettings,
    NextcloudSettings,
    load_database_url,
    load_immich_settings,
    load_nextcloud_settings,
)
from pdi.database import create_postgres_engine
from pdi.data_status import DataStatusService, PipelineRunRepository
from pdi.query import QueryService
from pdi.resource_query import ResourceQueryService
from pdi.resource_access import (
    NextcloudTextAdapter,
    ResourceTextService,
    create_immich_resource_access_runtime,
)
from pdi.observation import (
    ObservationService,
    PostgreSQLObservationRepository,
)
from pdi.repository import PostgreSQLRepository
from pdi.rich_retrieval import RichRetrievalService
from pdi.retrieval import RetrievalService
from pdi.retrieval.providers import ImmichSemanticRetrievalAdapter
from pdi.sync_state import PostgreSQLProviderSyncStateRepository

from .server import create_server


def create_runtime_server(
    database_url: str,
    immich_settings: ImmichSettings | None = None,
    nextcloud_settings: NextcloudSettings | None = None,
) -> MCPServer:
    engine = create_postgres_engine(database_url)
    repository = PostgreSQLRepository(engine)
    query_service = QueryService(repository)
    observation_service = ObservationService(
        PostgreSQLObservationRepository(engine)
    )
    retrieval_service = None
    resource_access_runtime = None
    if immich_settings is not None:
        retrieval_service = RetrievalService(
            ImmichSemanticRetrievalAdapter(
                immich_settings.url,
                immich_settings.api_key,
            ),
            repository,
        )
        resource_access_runtime = create_immich_resource_access_runtime(
            repository,
            base_url=immich_settings.url,
            api_key=immich_settings.api_key,
        )
    rich_retrieval_service = RichRetrievalService(
        repository,
        retrieval_service,
    )
    text_adapters = {}
    if nextcloud_settings is not None:
        nextcloud_text = NextcloudTextAdapter(
            nextcloud_settings.url,
            nextcloud_settings.user,
            nextcloud_settings.password,
        )
        text_adapters[nextcloud_text.provider] = nextcloud_text
    return create_server(
        query_service,
        observation_service,
        retrieval_service,
        rich_retrieval_service,
        DataStatusService(
            PipelineRunRepository(engine),
            sync_state_repository=PostgreSQLProviderSyncStateRepository(
                engine
            ),
        ),
        ResourceQueryService(
            query_service,
            rich_retrieval_service,
        ),
        ResourceTextService(repository, text_adapters),
        resource_access_service=(
            None
            if resource_access_runtime is None
            else resource_access_runtime.service
        ),
        resource_access_close=(
            None
            if resource_access_runtime is None
            else resource_access_runtime.aclose
        ),
    )


def main() -> None:
    try:
        immich_settings = load_immich_settings()
    except RuntimeError:
        immich_settings = None
    try:
        nextcloud_settings = load_nextcloud_settings()
    except RuntimeError:
        nextcloud_settings = None
    server = create_runtime_server(
        load_database_url(),
        immich_settings,
        nextcloud_settings,
    )
    server.run(transport="stdio")
