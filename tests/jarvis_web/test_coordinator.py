import asyncio

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from jarvis.runtime import ActiveTurnRegistry
from jarvis.state import Base, JarvisStateStore
from jarvis.state.database import create_session_factory
from jarvis.web.coordinator import TurnCoordinator


class FailingStartRuntime:
    async def start_turn(self, context) -> None:
        raise RuntimeError("synthetic private detail")

    async def cancel_turn(self, turn_id) -> None:
        return None

    async def stream_events(self, turn_id):
        if False:
            yield


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
