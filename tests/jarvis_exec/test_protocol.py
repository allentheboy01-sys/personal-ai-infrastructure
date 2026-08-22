from pathlib import Path

import anyio
from mcp import ClientSession

from jarvis.exec.contract import EXEC_TOOL_NAMES
from jarvis.exec.server import create_server
from jarvis.exec.workspace import Workspace


def test_mcp_initialize_and_tool_listing(tmp_path: Path) -> None:
    async def scenario() -> None:
        workspace = Workspace(tmp_path / "workspace")
        try:
            server = create_server(workspace)
            client_writer, server_reader = anyio.create_memory_object_stream(0)
            server_writer, client_reader = anyio.create_memory_object_stream(0)

            async with anyio.create_task_group() as tasks:
                tasks.start_soon(
                    server._lowlevel_server.run,
                    server_reader,
                    server_writer,
                    server._lowlevel_server.create_initialization_options(),
                )
                async with ClientSession(client_reader, client_writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert tuple(tool.name for tool in tools.tools) == EXEC_TOOL_NAMES
                tasks.cancel_scope.cancel()
        finally:
            workspace.close()

    anyio.run(scenario)
