import logging
from time import perf_counter

from .call import ToolCall
from .result import ToolResult
from .tools.registry import ToolNotFoundError, ToolRegistry


logger = logging.getLogger(__name__)


class JarvisApplication:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def execute(self, call: ToolCall) -> ToolResult:
        started_at = perf_counter()
        argument_keys = sorted(call.arguments)

        logger.info(
            "Tool execution started tool_name=%s argument_keys=%s",
            call.name,
            argument_keys,
        )

        try:
            tool = self._registry.get(call.name)
            result = tool.execute(call.arguments)
        except ToolNotFoundError:
            logger.warning(
                "Tool execution rejected tool_name=%s "
                "reason=unknown_tool",
                call.name,
            )
            result = ToolResult.fail(
                code="unknown_tool",
                message="The requested tool is not available.",
            )
        except Exception:
            logger.exception(
                "Tool execution failed tool_name=%s",
                call.name,
            )
            result = ToolResult.fail(
                code="internal_error",
                message="The tool could not be executed.",
            )

        duration_ms = (perf_counter() - started_at) * 1000
        logger.info(
            "Tool execution completed tool_name=%s success=%s "
            "duration_ms=%.3f",
            call.name,
            str(result.success).lower(),
            duration_ms,
        )

        return result
