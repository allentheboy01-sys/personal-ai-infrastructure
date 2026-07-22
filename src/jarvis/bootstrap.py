from pdi.config import Settings
from pdi.database import create_postgres_engine
from pdi.query import QueryService
from pdi.repository import PostgreSQLRepository

from .application import JarvisApplication
from .tools import GetAssetTool, ListAssetsTool, ToolRegistry


def create_jarvis_application(
    settings: Settings,
) -> JarvisApplication:
    engine = create_postgres_engine(settings.database.url)
    repository = PostgreSQLRepository(engine)
    query_service = QueryService(repository)

    registry = ToolRegistry()
    registry.register(ListAssetsTool(query_service))
    registry.register(GetAssetTool(query_service))

    return JarvisApplication(registry)
