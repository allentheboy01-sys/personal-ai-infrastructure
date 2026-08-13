from collections.abc import Callable
from datetime import datetime

from mcp.server import MCPServer

from pdi.query import InvalidQueryError, QueryError, QueryService
from pdi.observation import ObservationError, ObservationService

from .serialization import (
    serialize_resource_aggregation,
    serialize_resource_detail,
    serialize_resource_summary,
    serialize_statement,
)


ToolResult = dict[str, object]


def _error_result(error: QueryError | ObservationError) -> ToolResult:
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
    except (QueryError, ObservationError) as error:
        return _error_result(error)


def _datetime_argument(
    value: str | None,
    name: str,
) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InvalidQueryError(
            f"{name} must be an ISO 8601 datetime"
        )
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError as error:
        raise InvalidQueryError(
            f"{name} must be an ISO 8601 datetime"
        ) from error


def create_server(
    query_service: QueryService,
    observation_service: ObservationService | None = None,
) -> MCPServer:
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
        days: int | None = None,
        provider: str | None = None,
        resource_type: str | None = None,
        mime_type: str | None = None,
        path_prefix: str | None = None,
        limit: int = 50,
        observed_from: str | None = None,
        observed_to: str | None = None,
        cursor: str | None = None,
        mime_category: str | None = None,
    ) -> ToolResult:
        """List resources recently first identified by PDI.

        The returned time represents when PDI first created the resource
        record. It does not prove when the user created, uploaded, modified,
        or completed the resource.
        """

        def operation() -> ToolResult:
            page = query_service.list_resource_page(
                days=days,
                observed_from=_datetime_argument(
                    observed_from,
                    "observed_from",
                ),
                observed_to=_datetime_argument(
                    observed_to,
                    "observed_to",
                ),
                provider=provider,
                resource_type=resource_type,
                mime_type=mime_type,
                mime_category=mime_category,
                path_prefix=path_prefix,
                limit=limit,
                cursor=cursor,
            )
            return {
                "ok": True,
                "resources": [
                    serialize_resource_summary(resource)
                    for resource in page.resources
                ],
                "next_cursor": page.next_cursor,
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
        observed_from: str | None = None,
        observed_to: str | None = None,
        cursor: str | None = None,
        mime_category: str | None = None,
    ) -> ToolResult:
        """Search PDI resource title, source name, and source path metadata."""

        def operation() -> ToolResult:
            page = query_service.search_resource_page(
                query=query,
                observed_from=_datetime_argument(
                    observed_from,
                    "observed_from",
                ),
                observed_to=_datetime_argument(
                    observed_to,
                    "observed_to",
                ),
                provider=provider,
                resource_type=resource_type,
                mime_type=mime_type,
                mime_category=mime_category,
                path_prefix=path_prefix,
                limit=limit,
                cursor=cursor,
            )
            return {
                "ok": True,
                "resources": [
                    serialize_resource_summary(resource)
                    for resource in page.resources
                ],
                "next_cursor": page.next_cursor,
            }

        return _query_call(operation)

    @server.tool(structured_output=True)
    def pdi_aggregate_resources(
        group_by: str | None = None,
        observed_from: str | None = None,
        observed_to: str | None = None,
        provider: str | None = None,
        resource_type: str | None = None,
        mime_type: str | None = None,
        mime_category: str | None = None,
        path_prefix: str | None = None,
    ) -> ToolResult:
        """Count or group Resources by PDI first-observed time.

        This aggregation describes when PDI first recognized Resources. It
        does not describe capture, upload, user creation, provider creation,
        or provider modification time.
        """

        def operation() -> ToolResult:
            result = query_service.aggregate_resources(
                group_by=group_by,
                observed_from=_datetime_argument(
                    observed_from,
                    "observed_from",
                ),
                observed_to=_datetime_argument(
                    observed_to,
                    "observed_to",
                ),
                provider=provider,
                resource_type=resource_type,
                mime_type=mime_type,
                mime_category=mime_category,
                path_prefix=path_prefix,
            )
            return {
                "ok": True,
                **serialize_resource_aggregation(result),
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

    @server.tool(structured_output=True)
    def pdi_get_resource_observations(
        resource_ref: str,
        predicate: str | None = None,
    ) -> ToolResult:
        """Get current typed observations for one PDI Resource.

        Observations are provenance-bearing claims made by a named generator;
        they are not a single universal truth or PDI first-observed time.
        """

        def operation() -> ToolResult:
            if observation_service is None:
                raise ObservationError(
                    "Observation service is unavailable"
                )
            statements = observation_service.get_resource_statements(
                resource_ref,
                predicate=predicate,
                include_history=False,
                limit=100,
            )
            return {
                "ok": True,
                "observations": [
                    serialize_statement(statement)
                    for statement in statements
                ],
            }

        return _query_call(operation)

    return server
