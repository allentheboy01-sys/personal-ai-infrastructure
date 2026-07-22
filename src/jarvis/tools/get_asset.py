from collections.abc import Mapping
from uuid import UUID

from pdi.query.service import QueryService

from jarvis.result import ToolResult


class GetAssetTool:
    name = "get_asset"
    description = "Get one asset from PDI by asset ID."

    def __init__(self, query_service: QueryService) -> None:
        self._query_service = query_service

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> ToolResult:
        if set(arguments) != {"asset_id"}:
            return self._invalid_arguments()

        asset_id = arguments["asset_id"]

        if not isinstance(asset_id, str):
            return self._invalid_arguments()

        try:
            normalized_asset_id = str(UUID(asset_id))
        except ValueError:
            return self._invalid_arguments()

        asset = self._query_service.get_asset(
            normalized_asset_id
        )

        if asset is None:
            return ToolResult.fail(
                code="asset_not_found",
                message="The requested asset was not found.",
            )

        return ToolResult.ok(asset)

    @staticmethod
    def _invalid_arguments() -> ToolResult:
        return ToolResult.fail(
            code="invalid_arguments",
            message="asset_id must be a valid UUID string.",
        )
