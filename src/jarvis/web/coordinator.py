import asyncio
from uuid import UUID

from jarvis.runtime import ActiveTurnRegistry, ConversationEntry, RuntimeAdapter, RuntimeEvent, RuntimeEventType, TurnContext
from jarvis.state import JarvisStateStore


class TurnCoordinator:
    def __init__(self, state: JarvisStateStore, runtime: RuntimeAdapter, registry: ActiveTurnRegistry) -> None:
        self._state = state
        self._runtime = runtime
        self._registry = registry
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self, conversation_id: UUID, body: str) -> UUID:
        turn = self._state.create_turn(conversation_id, body)
        history = tuple(ConversationEntry(message.role, message.body) for message in self._state.history_for_turn(turn.id) if message.id != turn.user_message_id)
        context = TurnContext(turn.id, history, body)
        self._registry.register(turn.id)
        try:
            await self._runtime.start_turn(context)
        except Exception:
            self._state.finish_without_message(turn.id, "failed", "runtime_start_failed")
            await self._registry.publish(RuntimeEvent(turn.id, 1, RuntimeEventType.TURN_FAILED, error_code="runtime_start_failed"))
            return turn.id
        task = asyncio.create_task(self._consume(turn.id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return turn.id

    async def cancel(self, turn_id: UUID) -> None:
        turn = self._state.get_turn(turn_id)
        if turn.status != "running":
            return
        await self._runtime.cancel_turn(turn_id)
        for _ in range(100):
            snapshot = self._registry.snapshot(turn_id)
            if snapshot is not None and snapshot.terminal_event is not None:
                return
            await asyncio.sleep(0.002)

    async def _consume(self, turn_id: UUID) -> None:
        try:
            async for event in self._runtime.stream_events(turn_id):
                self._registry.validate_next(event)
                if event.type == RuntimeEventType.TURN_COMPLETED:
                    snapshot = self._registry.snapshot(turn_id)
                    body = snapshot.provisional_text if snapshot else ""
                    try:
                        self._state.complete_turn(turn_id, body, event.resource_refs)
                    except Exception:
                        failed = RuntimeEvent(turn_id, event.sequence, RuntimeEventType.TURN_FAILED, error_code="state_commit_failed")
                        self._state.finish_without_message(turn_id, "failed", "state_commit_failed")
                        await self._registry.publish(failed)
                        return
                elif event.type == RuntimeEventType.TURN_FAILED:
                    self._state.finish_without_message(turn_id, "failed", event.error_code or "runtime_failed")
                elif event.type == RuntimeEventType.TURN_CANCELLED:
                    self._state.finish_without_message(turn_id, "cancelled")
                await self._registry.publish(event)
        except Exception:
            turn = self._state.get_turn(turn_id)
            if turn.status == "running":
                self._state.finish_without_message(turn_id, "failed", "runtime_stream_failed")
                snapshot = self._registry.snapshot(turn_id)
                sequence = (snapshot.sequence if snapshot else 0) + 1
                await self._registry.publish(RuntimeEvent(turn_id, sequence, RuntimeEventType.TURN_FAILED, error_code="runtime_stream_failed"))
