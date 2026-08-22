"""Frozen V0.1 Jarvis Exec MCP contract."""

EXEC_TOOL_NAMES = (
    "jarvis_exec_python",
    "jarvis_workspace_write_text",
    "jarvis_workspace_read_text",
    "jarvis_workspace_list",
    "jarvis_workspace_delete",
)

WORKSPACE_BYTES = 16 * 1024 * 1024
MAX_FILES = 64
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_STDOUT_BYTES = 64 * 1024
MAX_STDERR_BYTES = 32 * 1024
EXECUTION_TIMEOUT_SECONDS = 30
