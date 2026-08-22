from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


MAX_PRESENTED_RESOURCES_PER_ASSISTANT_MESSAGE = 8


def is_canonical_resource_ref(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("pdi:resource:"):
        return False
    raw_uuid = value[len("pdi:resource:") :]
    try:
        parsed = UUID(raw_uuid)
    except (ValueError, AttributeError):
        return False
    return raw_uuid == str(parsed)


class RuntimeEventType(StrEnum):
    TURN_STARTED = "turn.started"
    PHASE_CHANGED = "phase.changed"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    MESSAGE_DELTA = "message.delta"
    TURN_COMPLETED = "turn.completed"
    TURN_FAILED = "turn.failed"
    TURN_CANCELLED = "turn.cancelled"


class RuntimePhase(StrEnum):
    THINKING = "thinking"
    SEARCHING = "searching"
    REVIEWING = "reviewing"
    COMPUTING = "computing"
    COMPOSING = "composing"


class RuntimeToolCategory(StrEnum):
    PDI = "pdi"
    EXEC = "exec"
    WEB = "web"
    ACTION = "action"
    OTHER = "other"


class RuntimeCapability(StrEnum):
    SEARCH_PERSONAL_RESOURCES = "search_personal_resources"
    READ_PERSONAL_RESOURCE = "read_personal_resource"
    REVIEW_PERSONAL_RESOURCES = "review_personal_resources"
    RUN_PYTHON = "run_python"
    WRITE_WORKSPACE = "write_workspace"
    READ_WORKSPACE = "read_workspace"
    MANAGE_WORKSPACE = "manage_workspace"
    USE_TOOL = "use_tool"


@dataclass(frozen=True, slots=True)
class ConversationEntry:
    role: str
    body: str


@dataclass(frozen=True, slots=True)
class TurnContext:
    turn_id: UUID
    history: tuple[ConversationEntry, ...]
    current_user_message: str
    attachment_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    turn_id: UUID
    sequence: int
    type: RuntimeEventType
    phase: RuntimePhase | None = None
    delta: str | None = None
    error_code: str | None = None
    resource_refs: tuple[str, ...] = ()
    operation_id: int | None = None
    category: RuntimeToolCategory | None = None
    capability: RuntimeCapability | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        if self.type == RuntimeEventType.TURN_COMPLETED:
            if (
                not isinstance(self.resource_refs, tuple)
                or len(self.resource_refs) > MAX_PRESENTED_RESOURCES_PER_ASSISTANT_MESSAGE
                or any(not is_canonical_resource_ref(value) for value in self.resource_refs)
                or len(set(self.resource_refs)) != len(self.resource_refs)
            ):
                raise ValueError("invalid completed resource refs")
        elif self.resource_refs != ():
            raise ValueError("resource refs require a completed turn")
        tool_event = self.type in {RuntimeEventType.TOOL_STARTED, RuntimeEventType.TOOL_COMPLETED}
        tool_fields = (self.operation_id, self.category, self.capability, self.duration_ms)
        if not tool_event:
            if any(value is not None for value in tool_fields):
                raise ValueError("tool payload requires a tool event")
            return
        if (
            isinstance(self.operation_id, bool)
            or not isinstance(self.operation_id, int)
            or not 1 <= self.operation_id <= 32
            or not isinstance(self.category, RuntimeToolCategory)
            or not isinstance(self.capability, RuntimeCapability)
            or self.phase is not None
            or self.delta is not None
            or self.error_code is not None
            or self.resource_refs
        ):
            raise ValueError("invalid tool event payload")
        if self.type == RuntimeEventType.TOOL_STARTED:
            if self.duration_ms is not None:
                raise ValueError("tool start cannot contain duration")
        elif (
            isinstance(self.duration_ms, bool)
            or not isinstance(self.duration_ms, int)
            or not 0 <= self.duration_ms <= 600_000
        ):
            raise ValueError("invalid tool completion duration")


class RuntimeAdapter(Protocol):
    async def start_turn(self, context: TurnContext) -> None: ...
    def stream_events(self, turn_id: UUID) -> AsyncIterator[RuntimeEvent]: ...
    async def cancel_turn(self, turn_id: UUID) -> None: ...
