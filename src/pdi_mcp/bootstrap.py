from mcp.server import MCPServer

from pdi.config.settings import load_database_url
from pdi.database import create_postgres_engine
from pdi.query import QueryService
from pdi.repository import PostgreSQLRepository

from .server import create_server


def create_runtime_server(database_url: str) -> MCPServer:
    engine = create_postgres_engine(database_url)
    repository = PostgreSQLRepository(engine)
    query_service = QueryService(repository)
    return create_server(query_service)


def main() -> None:
    server = create_runtime_server(load_database_url())
    server.run(transport="stdio")
