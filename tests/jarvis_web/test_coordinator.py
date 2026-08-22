import asyncio
from uuid import uuid4

import pytest

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from jarvis.runtime import ActiveTurnRegistry, RuntimeEvent, RuntimeEventType
from jarvis.state import Base, JarvisStateStore
from jarvis.state.database import create_session_factory
from jarvis.web.coordinator import TurnCoordinator


TERMINAL_TYPES = {
    RuntimeEventType.TURN_COMPLETED,
    RuntimeEventType.TURN_FAILED,
    RuntimeEventType.TURN_CANCELLED,
}


class FailingStartRuntime:
    async def start_turn(self, context) -> None:
        raise RuntimeError("synthetic private detail")

    async def cancel_turn(self, turn_id) -> None:
        return None

    async def stream_events(self, turn_id):
        if False:
            yield


class ControlledTerminalRuntime:
    def __init__(self, terminal: RuntimeEventType) -> None:
        self.terminal = terminal
        self.cancel_called = asyncio.Event()
        self.release_terminal = asyncio.Event()
        self.cancel_calls = 0
        self._queues = {}
        self._tasks = {}

    async def start_turn(self, context) -> None:
        queue = asyncio.Queue()
        self._queues[context.turn_id] = queue
        await queue.put(RuntimeEvent(context.turn_id, 1, RuntimeEventType.TURN_STARTED))
        self._tasks[context.turn_id] = asyncio.create_task(self._emit_terminal(context.turn_id))

    async def cancel_turn(self, turn_id) -> None:
        self.cancel_calls += 1
        self.cancel_called.set()

    async def stream_events(self, turn_id):
        while True:
            event = await self._queues[turn_id].get()
            yield event
            if event.type in TERMINAL_TYPES:
                return

    async def _emit_terminal(self, turn_id) -> None:
        await self.cancel_called.wait()
        await self.release_terminal.wait()
        queue = self._queues[turn_id]
        sequence = 2
        if self.terminal == RuntimeEventType.TURN_COMPLETED:
            await queue.put(RuntimeEvent(turn_id, sequence, RuntimeEventType.MESSAGE_DELTA, delta="synthetic final"))
            sequence += 1
        await queue.put(
            RuntimeEvent(
                turn_id,
                sequence,
                self.terminal,
                error_code="synthetic_failure" if self.terminal == RuntimeEventType.TURN_FAILED else None,
            )
        )


def _coordinator(runtime):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    state = JarvisStateStore(create_session_factory(engine))
    registry = ActiveTurnRegistry()
    return engine, state, registry, TurnCoordinator(state, runtime, registry)


def test_runtime_start_failure_is_sanitized_and_terminal() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    state = JarvisStateStore(create_session_factory(engine))
    registry = ActiveTurnRegistry()
    coordinator = TurnCoordinator(state, FailingStartRuntime(), registry)
    conversation = state.create_conversation()

    turn_id = asyncio.run(coordinator.start(conversation.id, "hello"))

    turn = state.get_turn(turn_id)
    assert turn.status == "failed"
    assert turn.error_code == "runtime_start_failed"
    assert turn.assistant_message_id is None
    assert registry.snapshot(turn_id).terminal_event.value == "turn.failed"


def test_cancel_waits_for_delayed_terminal_state_and_is_idempotent() -> None:
    async def scenario():
        runtime = ControlledTerminalRuntime(RuntimeEventType.TURN_CANCELLED)
        engine, state, registry, coordinator = _coordinator(runtime)
        conversation = state.create_conversation()
        turn_id = await coordinator.start(conversation.id, "hello")
        assert coordinator._tasks.get(turn_id) is not None

        cancelling = asyncio.create_task(coordinator.cancel(turn_id))
        await runtime.cancel_called.wait()
        await asyncio.sleep(0.25)
        assert not cancelling.done()
        runtime.release_terminal.set()
        await asyncio.wait_for(cancelling, timeout=1)
        await coordinator.cancel(turn_id)
        await asyncio.sleep(0)

        turn = state.get_turn(turn_id)
        events = [event async for event in registry.stream(turn_id)]
        assert turn_id not in coordinator._tasks
        engine.dispose()
        return runtime, turn, events

    runtime, turn, events = asyncio.run(scenario())
    assert runtime.cancel_calls == 1
    assert turn.status == "cancelled"
    assert turn.assistant_message_id is None
    assert [event.type for event in events if event.type in TERMINAL_TYPES] == [RuntimeEventType.TURN_CANCELLED]


@pytest.mark.parametrize(
    ("terminal", "expected_status", "assistant_expected"),
    [
        (RuntimeEventType.TURN_COMPLETED, "completed", True),
        (RuntimeEventType.TURN_FAILED, "failed", False),
    ],
)
def test_terminal_event_wins_race_with_cancel(terminal, expected_status, assistant_expected) -> None:
    async def scenario():
        runtime = ControlledTerminalRuntime(terminal)
        engine, state, registry, coordinator = _coordinator(runtime)
        conversation = state.create_conversation()
        turn_id = await coordinator.start(conversation.id, "hello")
        cancelling = asyncio.create_task(coordinator.cancel(turn_id))
        await runtime.cancel_called.wait()
        runtime.release_terminal.set()
        await asyncio.wait_for(cancelling, timeout=1)
        await asyncio.sleep(0)
        turn = state.get_turn(turn_id)
        events = [event async for event in registry.stream(turn_id)]
        assert turn_id not in coordinator._tasks
        engine.dispose()
        return turn, events

    turn, events = asyncio.run(scenario())
    assert turn.status == expected_status
    assert (turn.assistant_message_id is not None) is assistant_expected
    terminals = [event.type for event in events if event.type in TERMINAL_TYPES]
    assert terminals == [terminal]


def test_http_cancellation_cannot_cancel_canonical_consumer() -> None:
    async def scenario():
        runtime = ControlledTerminalRuntime(RuntimeEventType.TURN_CANCELLED)
        engine, state, _, coordinator = _coordinator(runtime)
        conversation = state.create_conversation()
        turn_id = await coordinator.start(conversation.id, "hello")
        consumer = coordinator._tasks[turn_id]

        request = asyncio.create_task(coordinator.cancel(turn_id))
        await runtime.cancel_called.wait()
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        assert not consumer.cancelled()

        runtime.release_terminal.set()
        await asyncio.wait_for(consumer, timeout=1)
        await asyncio.sleep(0)
        turn = state.get_turn(turn_id)
        assert turn.status == "cancelled"
        assert turn.assistant_message_id is None
        assert turn_id not in coordinator._tasks
        engine.dispose()

    asyncio.run(scenario())


def test_completed_task_cannot_discard_different_mapping() -> None:
    async def scenario():
        runtime = ControlledTerminalRuntime(RuntimeEventType.TURN_CANCELLED)
        engine, _, _, coordinator = _coordinator(runtime)
        turn_id = uuid4()
        old = asyncio.create_task(asyncio.sleep(0))
        current = asyncio.create_task(asyncio.sleep(0.01))
        coordinator._tasks[turn_id] = current
        coordinator._discard_task(turn_id, old)
        assert coordinator._tasks[turn_id] is current
        await old
        await current
        coordinator._discard_task(turn_id, current)
        assert turn_id not in coordinator._tasks
        engine.dispose()

    asyncio.run(scenario())
