import asyncio
from collections import OrderedDict, deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID

from .contract import RuntimeEvent, RuntimeEventType, RuntimePhase


_TERMINAL_EVENTS = {RuntimeEventType.TURN_COMPLETED, RuntimeEventType.TURN_FAILED, RuntimeEventType.TURN_CANCELLED}


@dataclass(frozen=True, slots=True)
class TurnSnapshot:
    turn_id: UUID
    sequence: int
    phase: RuntimePhase | None
    provisional_text: str
    terminal_event: RuntimeEventType | None


@dataclass(slots=True)
class _ActiveTurn:
    events: deque[RuntimeEvent]
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    phase: RuntimePhase | None = None
    text: str = ""
    sequence: int = 0
    terminal: RuntimeEventType | None = None


class ActiveTurnRegistry:
    def __init__(self, replay_limit: int = 128, turn_limit: int = 128) -> None:
        self._turns: OrderedDict[UUID, _ActiveTurn] = OrderedDict()
        self._replay_limit = replay_limit
        self._turn_limit = turn_limit

    def register(self, turn_id: UUID) -> None:
        if turn_id in self._turns:
            raise RuntimeError("turn already registered")
        self._turns[turn_id] = _ActiveTurn(events=deque(maxlen=self._replay_limit))
        while len(self._turns) > self._turn_limit:
            oldest_id, oldest = next(iter(self._turns.items()))
            if oldest.terminal is None:
                break
            self._turns.pop(oldest_id)

    def contains(self, turn_id: UUID) -> bool:
        return turn_id in self._turns

    async def publish(self, event: RuntimeEvent) -> None:
        active = self._turns[event.turn_id]
        async with active.condition:
            self._validate(active, event)
            active.sequence = event.sequence
            if event.phase is not None:
                active.phase = event.phase
            if event.delta is not None:
                active.text += event.delta
            if event.type in _TERMINAL_EVENTS:
                active.terminal = event.type
            active.events.append(event)
            active.condition.notify_all()

    def validate_next(self, event: RuntimeEvent) -> None:
        self._validate(self._turns[event.turn_id], event)

    @staticmethod
    def _validate(active: _ActiveTurn, event: RuntimeEvent) -> None:
        if active.terminal is not None:
            raise RuntimeError("terminal event already published")
        if event.sequence != active.sequence + 1:
            raise RuntimeError("runtime event sequence is not monotonic")

    def snapshot(self, turn_id: UUID) -> TurnSnapshot | None:
        active = self._turns.get(turn_id)
        if active is None:
            return None
        return TurnSnapshot(turn_id, active.sequence, active.phase, active.text, active.terminal)

    async def stream(self, turn_id: UUID, after_sequence: int = 0) -> AsyncIterator[RuntimeEvent]:
        active = self._turns[turn_id]
        cursor = after_sequence
        while True:
            async with active.condition:
                available = [event for event in active.events if event.sequence > cursor]
                if not available and active.terminal is None:
                    await active.condition.wait_for(lambda: active.sequence > cursor or active.terminal is not None)
                    available = [event for event in active.events if event.sequence > cursor]
            for event in available:
                cursor = event.sequence
                yield event
                if event.type in _TERMINAL_EVENTS:
                    return
            if active.terminal is not None:
                return
