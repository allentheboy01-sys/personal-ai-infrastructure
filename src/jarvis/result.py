from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True, slots=True)
class ToolError:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ToolResult:
    data: object | None = None
    error: ToolError | None = None

    def __post_init__(self) -> None:
        if self.data is not None and self.error is not None:
            raise ValueError(
                "ToolResult cannot contain both data and error"
            )

    @property
    def success(self) -> bool:
        return self.error is None

    @classmethod
    def ok(cls, data: object | None = None) -> Self:
        return cls(data=data)

    @classmethod
    def fail(cls, code: str, message: str) -> Self:
        return cls(error=ToolError(code=code, message=message))
