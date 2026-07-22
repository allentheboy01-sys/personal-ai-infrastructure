from collections.abc import Mapping
from typing import Protocol

from jarvis.result import ToolResult


class Tool(Protocol):
    name: str
    description: str

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> ToolResult:
        ...
