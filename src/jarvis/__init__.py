"""Jarvis package.

Legacy tool-facade exports remain lazy so the independent Web distribution can
import its product modules without installing PDI implementation packages.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "JarvisApplication",
    "ToolCall",
    "ToolError",
    "ToolResult",
]


def __getattr__(name: str) -> Any:
    if name == "JarvisApplication":
        from .application import JarvisApplication

        return JarvisApplication
    if name == "ToolCall":
        from .call import ToolCall

        return ToolCall
    if name in {"ToolError", "ToolResult"}:
        from .result import ToolError, ToolResult

        return {"ToolError": ToolError, "ToolResult": ToolResult}[name]
    raise AttributeError(name)
