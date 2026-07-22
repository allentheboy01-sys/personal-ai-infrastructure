from collections.abc import Mapping

from pdi.query.service import QueryService

from jarvis.result import ToolResult


class ListAssetsTool:
    name = "list_assets"
    description = "List assets available in PDI."

    def __init__(self, query_service: QueryService) -> None:
        self._query_service = query_service

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> ToolResult:
        if arguments:
            return ToolResult.fail(
                code="invalid_arguments",
                message="list_assets does not accept arguments.",
            )

        return ToolResult.ok(
            self._query_service.list_assets()
        )
