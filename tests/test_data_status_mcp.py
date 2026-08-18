import asyncio
from datetime import UTC, datetime, timedelta

from mcp import Client

from pdi.data_status import (
    PipelineErrorCode,
    PipelineKind,
    PipelineStatus,
    PipelineStatusView,
    StatusSnapshot,
)
from pdi.query import QueryService
from pdi_mcp import create_server
from tests.test_pdi_mcp import RecordingRepository


NOW = datetime(2026, 8, 18, 6, tzinfo=UTC)


class FakeDataStatusService:
    def get_status(self) -> StatusSnapshot:
        return StatusSnapshot(
            NOW,
            (
                PipelineStatusView(
                    pipeline_key="provider.immich.sync",
                    kind=PipelineKind.PROVIDER_SYNC,
                    latest_status=PipelineStatus.FAILED,
                    latest_started_at=NOW - timedelta(minutes=1),
                    latest_finished_at=NOW,
                    latest_error_code=PipelineErrorCode.EXECUTION_FAILED,
                    last_success_at=NOW - timedelta(days=1),
                    success_age_seconds=86400,
                    dependencies=(),
                    validated_after_dependencies=None,
                ),
            ),
        )


def test_data_status_tool_has_no_parameters_and_bounded_safe_output() -> None:
    server = create_server(
        QueryService(RecordingRepository()),
        data_status_service=FakeDataStatusService(),
    )

    async def exercise() -> None:
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            assert len(tools) == 8
            tool = next(tool for tool in tools if tool.name == "pdi_get_data_status")
            assert tool.input_schema["properties"] == {}
            result = await client.call_tool("pdi_get_data_status", {})
        payload = result.structured_content
        assert payload == {
            "ok": True,
            "generated_at": "2026-08-18T06:00:00+00:00",
            "pipelines": [
                {
                    "pipeline_key": "provider.immich.sync",
                    "kind": "provider_sync",
                    "latest_status": "failed",
                    "latest_started_at": "2026-08-18T05:59:00+00:00",
                    "latest_finished_at": "2026-08-18T06:00:00+00:00",
                    "latest_error_code": "execution_failed",
                    "last_success_at": "2026-08-17T06:00:00+00:00",
                    "success_age_seconds": 86400.0,
                    "dependencies": [],
                    "validated_after_dependencies": None,
                }
            ],
        }
        encoded = str(payload)
        for forbidden in (
            "run_id", "error_message", "traceback", "systemd", "journal"
        ):
            assert forbidden not in encoded

    asyncio.run(exercise())


def test_data_status_tool_description_freezes_semantic_limits() -> None:
    server = create_server(QueryService(RecordingRepository()))

    async def exercise() -> None:
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
        description = next(
            tool.description
            for tool in tools
            if tool.name == "pdi_get_data_status"
        )
        assert description is not None
        for term in (
            "data-pipeline", "CPU", "systemd", "live Provider",
            "currently identical", "fresh=true",
        ):
            assert term in description

    asyncio.run(exercise())
