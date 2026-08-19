from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class RuntimeEventType(StrEnum):
    TURN_STARTED = "turn.started"
    PHASE_CHANGED = "phase.changed"
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


class RuntimeAdapter(Protocol):
    async def start_turn(self, context: TurnContext) -> None: ...
    def stream_events(self, turn_id: UUID) -> AsyncIterator[RuntimeEvent]: ...
    async def cancel_turn(self, turn_id: UUID) -> None: ...
