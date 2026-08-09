from collections.abc import Callable

from mcp.server import MCPServer

from pdi.query import QueryError, QueryService

from .serialization import (
    serialize_resource_detail,
    serialize_resource_summary,
)


ToolResult = dict[str, object]


def _error_result(error: QueryError) -> ToolResult:
    return {
        "ok": False,
        "error": {
            "code": error.code,
            "message": str(error),
        },
    }


def _query_call(operation: Callable[[], ToolResult]) -> ToolResult:
    try:
        return operation()
    except QueryError as error:
        return _error_result(error)


def create_server(query_service: QueryService) -> MCPServer:
    server = MCPServer(
        name="pdi-personal-retrieval",
        instructions=(
            "Read-only access to resource metadata stored by PDI. "
            "Do not describe PDI observation times as user or provider "
            "creation, upload, modification, or completion times."
        ),
    )

    @server.tool(structured_output=True)
    def pdi_list_recent_resources(
        days: int = 30,
        provider: str | None = None,
        resource_type: str | None = None,
        mime_type: str | None = None,
        path_prefix: str | None = None,
        limit: int = 50,
    ) -> ToolResult:
        """List resources recently first identified by PDI.

        The returned time represents when PDI first created the resource
        record. It does not prove when the user created, uploaded, modified,
        or completed the resource.
        """

        def operation() -> ToolResult:
            resources = query_service.list_recent_resources(
                days=days,
                provider=provider,
                resource_type=resource_type,
                mime_type=mime_type,
                path_prefix=path_prefix,
                limit=limit,
            )
            return {
                "ok": True,
                "resources": [
                    serialize_resource_summary(resource)
                    for resource in resources
                ],
            }

        return _query_call(operation)

    @server.tool(structured_output=True)
    def pdi_search_resources(
        query: str,
        provider: str | None = None,
        resource_type: str | None = None,
        mime_type: str | None = None,
        path_prefix: str | None = None,
        limit: int = 50,
    ) -> ToolResult:
        """Search PDI resource title, source name, and source path metadata."""

        def operation() -> ToolResult:
            resources = query_service.search_resources(
                query=query,
                provider=provider,
                resource_type=resource_type,
                mime_type=mime_type,
                path_prefix=path_prefix,
                limit=limit,
            )
            return {
                "ok": True,
                "resources": [
                    serialize_resource_summary(resource)
                    for resource in resources
                ],
            }

        return _query_call(operation)

    @server.tool(structured_output=True)
    def pdi_get_resource(resource_ref: str) -> ToolResult:
        """Get one PDI resource projection by its resource reference."""

        def operation() -> ToolResult:
            resource = query_service.get_resource(resource_ref)
            return {
                "ok": True,
                "resource": serialize_resource_detail(resource),
            }

        return _query_call(operation)

    return server
