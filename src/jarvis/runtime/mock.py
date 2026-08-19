import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from .contract import RuntimeEvent, RuntimeEventType, RuntimePhase, TurnContext


@dataclass(slots=True)
class _MockSession:
    queue: asyncio.Queue[RuntimeEvent] = field(default_factory=asyncio.Queue)
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None


class MockRuntimeAdapter:
    """Deterministic implementation of the production RuntimeAdapter contract."""

    def __init__(self, *, scenario: Literal["normal", "failure"] = "normal", delay: float = 0.005) -> None:
        self._sessions: dict[UUID, _MockSession] = {}
        self._scenario = scenario
        self._delay = delay

    async def start_turn(self, context: TurnContext) -> None:
        if context.turn_id in self._sessions:
            raise RuntimeError("turn already started")
        session = _MockSession()
        self._sessions[context.turn_id] = session
        session.task = asyncio.create_task(self._run(context, session))

    async def cancel_turn(self, turn_id: UUID) -> None:
        session = self._sessions.get(turn_id)
        if session is not None:
            session.cancel.set()

    async def stream_events(self, turn_id: UUID) -> AsyncIterator[RuntimeEvent]:
        session = self._sessions[turn_id]
        while True:
            event = await session.queue.get()
            yield event
            if event.type in {RuntimeEventType.TURN_COMPLETED, RuntimeEventType.TURN_FAILED, RuntimeEventType.TURN_CANCELLED}:
                return

    async def _run(self, context: TurnContext, session: _MockSession) -> None:
        sequence = 0

        async def emit(event_type: RuntimeEventType, *, phase: RuntimePhase | None = None, delta: str | None = None, error_code: str | None = None) -> None:
            nonlocal sequence
            sequence += 1
            await session.queue.put(RuntimeEvent(context.turn_id, sequence, event_type, phase=phase, delta=delta, error_code=error_code))

        async def pause(delay: float) -> bool:
            try:
                await asyncio.wait_for(session.cancel.wait(), timeout=delay)
                return True
            except TimeoutError:
                return False

        await emit(RuntimeEventType.TURN_STARTED)
        for phase in (RuntimePhase.THINKING, RuntimePhase.SEARCHING):
            await emit(RuntimeEventType.PHASE_CHANGED, phase=phase)
            if await pause(self._delay):
                await emit(RuntimeEventType.TURN_CANCELLED)
                return
        if self._scenario == "failure":
            await emit(RuntimeEventType.TURN_FAILED, error_code="mock_controlled_failure")
            return
        await emit(RuntimeEventType.PHASE_CHANGED, phase=RuntimePhase.COMPOSING)
        chunks = ("I reviewed the available context. ", "This is a deterministic mock response ", "from the Jarvis runtime contract.")
        for chunk in chunks:
            if await pause(self._delay):
                await emit(RuntimeEventType.TURN_CANCELLED)
                return
            await emit(RuntimeEventType.MESSAGE_DELTA, delta=chunk)
        await emit(RuntimeEventType.TURN_COMPLETED)
