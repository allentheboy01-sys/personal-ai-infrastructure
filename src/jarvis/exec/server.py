"""Jarvis Exec MCP stdio server."""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server import MCPServer

from .execution import execute_python
from .workspace import Workspace, WorkspaceError


def create_server(workspace: Workspace) -> MCPServer:
    server = MCPServer(name="jarvis-exec", instructions="Bounded disposable Python and text workspace only.")

    def safe(operation):
        try:
            return operation()
        except (WorkspaceError, OSError) as error:
            code = str(error) if isinstance(error, WorkspaceError) else "workspace_unavailable"
            return {"ok": False, "error": code}

    @server.tool(structured_output=True)
    def jarvis_exec_python(code: str) -> dict[str, object]:
        """Execute bounded Python source inside the disposable workspace."""
        return execute_python(code, workspace.root)

    @server.tool(structured_output=True)
    def jarvis_workspace_write_text(path: str, text: str) -> dict[str, object]:
        """Write one bounded UTF-8 file using a workspace-relative path."""
        return safe(lambda: workspace.write_text(path, text))

    @server.tool(structured_output=True)
    def jarvis_workspace_read_text(path: str) -> dict[str, object]:
        """Read one bounded UTF-8 file using a workspace-relative path."""
        return safe(lambda: workspace.read_text(path))

    @server.tool(structured_output=True)
    def jarvis_workspace_list() -> dict[str, object]:
        """List bounded regular files in the disposable workspace."""
        return safe(workspace.list)

    @server.tool(structured_output=True)
    def jarvis_workspace_delete(path: str) -> dict[str, object]:
        """Delete one regular file using a workspace-relative path."""
        return safe(lambda: workspace.delete(path))

    return server


def main() -> None:
    root = os.environ.get("JARVIS_EXEC_WORKSPACE")
    if not root or not Path(root).is_absolute():
        raise SystemExit("jarvis-exec: workspace unavailable")
    workspace = Workspace(Path(root))
    try:
        create_server(workspace).run(transport="stdio")
    finally:
        workspace.close()


if __name__ == "__main__":
    main()
