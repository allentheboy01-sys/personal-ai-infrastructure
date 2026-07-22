from collections.abc import Mapping

import pytest

from jarvis import ToolResult
from jarvis.tools import (
    DuplicateToolError,
    ToolNotFoundError,
    ToolRegistry,
)


class FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.description = f"Description for {name}"

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> ToolResult:
        return ToolResult.ok()


def test_registry_registers_and_gets_tool() -> None:
    registry = ToolRegistry()
    tool = FakeTool("example")

    registry.register(tool)

    assert registry.get("example") is tool


def test_registry_rejects_duplicate_name() -> None:
    registry = ToolRegistry()
    registry.register(FakeTool("duplicate"))

    with pytest.raises(
        DuplicateToolError,
        match="duplicate",
    ):
        registry.register(FakeTool("duplicate"))


def test_registry_raises_specific_error_for_unknown_tool() -> None:
    registry = ToolRegistry()

    with pytest.raises(
        ToolNotFoundError,
        match="missing",
    ):
        registry.get("missing")


def test_registry_lists_tools_by_stable_name_order() -> None:
    registry = ToolRegistry()
    second = FakeTool("second")
    first = FakeTool("first")
    registry.register(second)
    registry.register(first)

    tools = registry.list_tools()

    assert tools == (first, second)
    assert isinstance(tools, tuple)
    assert registry.list_tools() == (first, second)
