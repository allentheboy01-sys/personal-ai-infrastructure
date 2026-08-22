import asyncio
from uuid import UUID

from jarvis.runtime import ActiveTurnRegistry, ConversationEntry, RuntimeAdapter, RuntimeEvent, RuntimeEventType, TurnContext
from jarvis.state import JarvisStateStore


_SHUTDOWN_CLEANUP_TIMEOUT_SECONDS = 8.0


class TurnCoordinator:
    def __init__(self, state: JarvisStateStore, runtime: RuntimeAdapter, registry: ActiveTurnRegistry) -> None:
        self._state = state
        self._runtime = runtime
        self._registry = registry
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._lifecycle_lock = asyncio.Lock()
        self._shutting_down = False

    async def start(self, conversation_id: UUID, body: str) -> UUID:
        async with self._lifecycle_lock:
            if self._shutting_down:
                raise RuntimeError("coordinator_shutting_down")
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
            self._tasks[turn.id] = task
            task.add_done_callback(lambda completed, turn_id=turn.id: self._discard_task(turn_id, completed))
            return turn.id

    async def cancel(self, turn_id: UUID) -> None:
        turn = self._state.get_turn(turn_id)
        if turn.status != "running":
            return
        await self._runtime.cancel_turn(turn_id)
        consumer = self._tasks.get(turn_id)
        if consumer is not None:
            await asyncio.shield(consumer)

    async def shutdown(self) -> None:
        """Take canonical ownership of active Turns before process teardown."""

        async with self._lifecycle_lock:
            if self._shutting_down:
                return
            self._shutting_down = True
            owned = tuple(self._tasks.items())
            interrupted: list[UUID] = []

            try:
                for turn_id, _ in owned:
                    turn = self._state.finish_without_message(turn_id, "interrupted", "process_restarted")
                    if turn.status == "interrupted" and turn.error_code == "process_restarted":
                        interrupted.append(turn_id)
            finally:
                # Once canonical interruption is committed, no process-local
                # Runtime terminal may rewrite it. Stop consumers before using
                # exact-Turn cancellation solely to clean Runtime children.
                # All process-local cleanup shares one deadline; systemd's
                # TimeoutStopSec remains the final cgroup cleanup authority.
                for _, task in owned:
                    task.cancel()

                cleanup_tasks = tuple(
                    asyncio.create_task(self._runtime.cancel_turn(turn_id))
                    for turn_id in interrupted
                )
                local_tasks = tuple(task for _, task in owned) + cleanup_tasks
                if local_tasks:
                    done, pending = await asyncio.wait(
                        local_tasks,
                        timeout=_SHUTDOWN_CLEANUP_TIMEOUT_SECONDS,
                    )
                    for task in done:
                        self._observe_task(task)
                    for task in pending:
                        task.add_done_callback(self._observe_task)
                        task.cancel()

                for turn_id, task in owned:
                    self._discard_task(turn_id, task)

    def _discard_task(self, turn_id: UUID, completed: asyncio.Task[None]) -> None:
        if self._tasks.get(turn_id) is completed:
            self._tasks.pop(turn_id)

    @staticmethod
    def _observe_task(task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except (asyncio.CancelledError, Exception):
            pass

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
