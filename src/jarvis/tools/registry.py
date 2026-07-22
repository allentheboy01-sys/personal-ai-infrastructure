from .protocol import Tool


class DuplicateToolError(Exception):
    pass


class ToolNotFoundError(Exception):
    pass


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise DuplicateToolError(
                f"Tool already registered: {tool.name}"
            )

        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(
                f"Tool not found: {name}"
            ) from None

    def list_tools(self) -> tuple[Tool, ...]:
        return tuple(
            self._tools[name]
            for name in sorted(self._tools)
        )
