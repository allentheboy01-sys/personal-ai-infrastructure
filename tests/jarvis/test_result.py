from dataclasses import FrozenInstanceError

import pytest

from jarvis import ToolCall, ToolError, ToolResult


def test_tool_call_is_immutable_and_detaches_arguments() -> None:
    arguments: dict[str, object] = {
        "asset_id": "asset-1",
    }
    call = ToolCall(
        name="get_asset",
        arguments=arguments,
    )

    arguments["asset_id"] = "changed"

    assert call.arguments["asset_id"] == "asset-1"

    with pytest.raises(TypeError):
        call.arguments["new"] = "value"

    with pytest.raises(FrozenInstanceError):
        call.name = "changed"


def test_tool_result_success_and_failure_states() -> None:
    success = ToolResult.ok(None)
    failure = ToolResult.fail(
        code="invalid_arguments",
        message="Invalid arguments.",
    )

    assert success.success is True
    assert success.data is None
    assert success.error is None
    assert failure.success is False
    assert failure.data is None
    assert failure.error == ToolError(
        code="invalid_arguments",
        message="Invalid arguments.",
    )


def test_tool_result_rejects_inconsistent_state() -> None:
    with pytest.raises(
        ValueError,
        match="both data and error",
    ):
        ToolResult(
            data="value",
            error=ToolError(
                code="error",
                message="Error.",
            ),
        )


def test_tool_result_is_immutable() -> None:
    result = ToolResult.ok("value")

    with pytest.raises(FrozenInstanceError):
        result.data = "changed"
