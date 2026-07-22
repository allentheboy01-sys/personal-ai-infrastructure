from collections.abc import Mapping
import logging

from jarvis import JarvisApplication, ToolCall, ToolResult
from jarvis.tools import ToolRegistry


class FakeTool:
    name = "fake"
    description = "A fake tool."

    def __init__(self, result: ToolResult) -> None:
        self.result = result
        self.received_arguments: Mapping[str, object] | None = None

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> ToolResult:
        self.received_arguments = arguments
        return self.result


class FailingTool:
    name = "failing"
    description = "A failing tool."

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> ToolResult:
        raise RuntimeError("private database detail")


def _application_with(tool) -> JarvisApplication:
    registry = ToolRegistry()
    registry.register(tool)
    return JarvisApplication(registry)


def test_application_executes_registered_tool_and_forwards_arguments(
    caplog,
) -> None:
    expected = ToolResult.ok("done")
    tool = FakeTool(expected)
    application = _application_with(tool)
    call = ToolCall(
        name="fake",
        arguments={"visible_key": "private value"},
    )

    with caplog.at_level(logging.INFO):
        result = application.execute(call)

    assert result is expected
    assert tool.received_arguments is call.arguments
    assert "Tool execution started" in caplog.text
    assert "Tool execution completed" in caplog.text
    assert "visible_key" in caplog.text
    assert "private value" not in caplog.text


def test_application_preserves_tool_business_error() -> None:
    expected = ToolResult.fail(
        code="invalid_arguments",
        message="Invalid arguments.",
    )
    application = _application_with(FakeTool(expected))

    result = application.execute(
        ToolCall(name="fake", arguments={})
    )

    assert result is expected


def test_application_converts_unknown_tool_to_stable_error(
    caplog,
) -> None:
    application = JarvisApplication(ToolRegistry())

    with caplog.at_level(logging.INFO):
        result = application.execute(
            ToolCall(name="missing", arguments={})
        )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "unknown_tool"
    assert result.error.message == (
        "The requested tool is not available."
    )
    assert "reason=unknown_tool" in caplog.text


def test_application_logs_and_hides_unexpected_exception(
    caplog,
) -> None:
    application = _application_with(FailingTool())

    with caplog.at_level(logging.INFO):
        result = application.execute(
            ToolCall(name="failing", arguments={})
        )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "internal_error"
    assert result.error.message == (
        "The tool could not be executed."
    )
    assert "Tool execution failed" in caplog.text
    assert "private database detail" in caplog.text
    assert caplog.records[-2].exc_info is not None
