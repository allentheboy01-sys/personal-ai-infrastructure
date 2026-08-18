from mcp.server import MCPServer

from pdi.config.settings import (
    ImmichSettings,
    load_database_url,
    load_immich_settings,
)
from pdi.database import create_postgres_engine
from pdi.data_status import DataStatusService, PipelineRunRepository
from pdi.query import QueryService
from pdi.observation import (
    ObservationService,
    PostgreSQLObservationRepository,
)
from pdi.repository import PostgreSQLRepository
from pdi.rich_retrieval import RichRetrievalService
from pdi.retrieval import RetrievalService
from pdi.retrieval.providers import ImmichSemanticRetrievalAdapter

from .server import create_server


def create_runtime_server(
    database_url: str,
    immich_settings: ImmichSettings | None = None,
) -> MCPServer:
    engine = create_postgres_engine(database_url)
    repository = PostgreSQLRepository(engine)
    query_service = QueryService(repository)
    observation_service = ObservationService(
        PostgreSQLObservationRepository(engine)
    )
    retrieval_service = None
    if immich_settings is not None:
        retrieval_service = RetrievalService(
            ImmichSemanticRetrievalAdapter(
                immich_settings.url,
                immich_settings.api_key,
            ),
            repository,
        )
    return create_server(
        query_service,
        observation_service,
        retrieval_service,
        RichRetrievalService(repository, retrieval_service),
        DataStatusService(PipelineRunRepository(engine)),
    )


def main() -> None:
    try:
        immich_settings = load_immich_settings()
    except RuntimeError:
        immich_settings = None
    server = create_runtime_server(
        load_database_url(),
        immich_settings,
    )
    server.run(transport="stdio")
