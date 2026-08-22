import asyncio
from uuid import uuid4

import pytest

from jarvis.runtime import (
    ActiveTurnRegistry,
    MockRuntimeAdapter,
    RuntimeCapability,
    RuntimeEvent,
    RuntimeEventType,
    RuntimeToolCategory,
    TurnContext,
)


async def _collect(adapter: MockRuntimeAdapter, context: TurnContext):
    await adapter.start_turn(context)
    return [event async for event in adapter.stream_events(context.turn_id)]


def test_mock_completion_is_monotonic_and_has_one_terminal_event() -> None:
    events = asyncio.run(_collect(MockRuntimeAdapter(delay=0), TurnContext(uuid4(), (), "hello")))
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    terminals = [event for event in events if event.type in {RuntimeEventType.TURN_COMPLETED, RuntimeEventType.TURN_FAILED, RuntimeEventType.TURN_CANCELLED}]
    assert [event.type for event in terminals] == [RuntimeEventType.TURN_COMPLETED]
    assert "".join(event.delta or "" for event in events) == "I reviewed the available context. This is a deterministic mock response from the Jarvis runtime contract."


def test_mock_failure_is_sanitized() -> None:
    events = asyncio.run(_collect(MockRuntimeAdapter(scenario="failure", delay=0), TurnContext(uuid4(), (), "ordinary user text")))
    assert events[-1].type == RuntimeEventType.TURN_FAILED
    assert events[-1].error_code == "mock_controlled_failure"
    assert all(event.delta is None for event in events)


def test_cancel_is_idempotent() -> None:
    async def scenario():
        adapter = MockRuntimeAdapter(delay=0.2)
        context = TurnContext(uuid4(), (), "wait")
        await adapter.start_turn(context)
        await adapter.cancel_turn(context.turn_id)
        await adapter.cancel_turn(context.turn_id)
        return [event async for event in adapter.stream_events(context.turn_id)]

    events = asyncio.run(scenario())
    assert events[-1].type == RuntimeEventType.TURN_CANCELLED
    assert sum(event.type == RuntimeEventType.TURN_CANCELLED for event in events) == 1


def test_registry_replays_after_sequence_and_exposes_snapshot() -> None:
    async def scenario():
        turn_id = uuid4()
        adapter = MockRuntimeAdapter(delay=0)
        registry = ActiveTurnRegistry()
        registry.register(turn_id)
        await adapter.start_turn(TurnContext(turn_id, (), "hello"))
        async for event in adapter.stream_events(turn_id):
            await registry.publish(event)
        replay = [event async for event in registry.stream(turn_id, after_sequence=3)]
        return registry.snapshot(turn_id), replay

    snapshot, replay = asyncio.run(scenario())
    assert snapshot is not None
    assert snapshot.terminal_event == RuntimeEventType.TURN_COMPLETED
    assert replay[0].sequence == 4
    assert replay[-1].type == RuntimeEventType.TURN_COMPLETED


def test_registry_replays_sanitized_tool_events_without_treating_them_as_terminal() -> None:
    async def scenario():
        turn_id = uuid4()
        registry = ActiveTurnRegistry()
        registry.register(turn_id)
        started = RuntimeEvent(
            turn_id,
            1,
            RuntimeEventType.TOOL_STARTED,
            operation_id=1,
            category=RuntimeToolCategory.EXEC,
            capability=RuntimeCapability.RUN_PYTHON,
        )
        completed = RuntimeEvent(
            turn_id,
            2,
            RuntimeEventType.TOOL_COMPLETED,
            operation_id=1,
            category=RuntimeToolCategory.EXEC,
            capability=RuntimeCapability.RUN_PYTHON,
            duration_ms=12,
        )
        terminal = RuntimeEvent(turn_id, 3, RuntimeEventType.TURN_COMPLETED)
        for event in (started, completed, terminal):
            await registry.publish(event)
        return [event async for event in registry.stream(turn_id)]

    replay = asyncio.run(scenario())
    assert [event.type for event in replay] == [RuntimeEventType.TOOL_STARTED, RuntimeEventType.TOOL_COMPLETED, RuntimeEventType.TURN_COMPLETED]


def test_runtime_event_rejects_unsafe_tool_payload_shapes() -> None:
    turn_id = uuid4()
    with pytest.raises(ValueError, match="invalid tool event payload"):
        RuntimeEvent(turn_id, 1, RuntimeEventType.TOOL_STARTED, operation_id=1)
    with pytest.raises(ValueError, match="tool start cannot contain duration"):
        RuntimeEvent(
            turn_id,
            1,
            RuntimeEventType.TOOL_STARTED,
            operation_id=1,
            category=RuntimeToolCategory.OTHER,
            capability=RuntimeCapability.USE_TOOL,
            duration_ms=1,
        )


def test_subscriber_disconnect_does_not_cancel_runtime() -> None:
    async def scenario():
        turn_id = uuid4()
        adapter = MockRuntimeAdapter(delay=0.001)
        registry = ActiveTurnRegistry()
        registry.register(turn_id)
        await adapter.start_turn(TurnContext(turn_id, (), "hello"))

        async def consume_runtime():
            async for event in adapter.stream_events(turn_id):
                await registry.publish(event)

        task = asyncio.create_task(consume_runtime())
        subscriber = registry.stream(turn_id)
        first = await anext(subscriber)
        await subscriber.aclose()
        await task
        return first, registry.snapshot(turn_id)

    first, snapshot = asyncio.run(scenario())
    assert first.type == RuntimeEventType.TURN_STARTED
    assert snapshot is not None
    assert snapshot.terminal_event == RuntimeEventType.TURN_COMPLETED
