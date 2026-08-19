from uuid import uuid4

import pytest
from sqlalchemy import event, func, select

from jarvis.state import ActiveTurnError, Message, StateConflictError, Turn


def test_conversation_and_completed_turn_are_canonical(state_store) -> None:
    conversation = state_store.create_conversation("  Project brief  ")
    turn = state_store.create_turn(conversation.id, "Help me draft it")
    state_store.complete_turn(turn.id, "Here is a concise draft.", [f"pdi:resource:{uuid4()}", f"pdi:resource:{uuid4()}"])

    restored = state_store.get_conversation(conversation.id)
    completed = state_store.get_turn(turn.id)

    assert restored.title == "Project brief"
    assert [(message.role, message.body) for message in restored.messages] == [("user", "Help me draft it"), ("assistant", "Here is a concise draft.")]
    assert [ref.ordinal for ref in restored.messages[1].resource_refs] == [0, 1]
    assert completed.status == "completed"
    assert completed.assistant_message_id == restored.messages[1].id


def test_one_active_turn_and_retry_creates_new_turn(state_store) -> None:
    conversation = state_store.create_conversation()
    first = state_store.create_turn(conversation.id, "first")
    with pytest.raises(ActiveTurnError):
        state_store.create_turn(conversation.id, "blocked")
    state_store.finish_without_message(first.id, "failed", "mock_failure")
    retry = state_store.create_turn(conversation.id, "retry")
    assert retry.id != first.id
    assert retry.status == "running"


def test_terminal_turn_never_returns_to_running(state_store) -> None:
    conversation = state_store.create_conversation()
    turn = state_store.create_turn(conversation.id, "hello")
    state_store.finish_without_message(turn.id, "cancelled")
    assert state_store.finish_without_message(turn.id, "cancelled").status == "cancelled"
    with pytest.raises(StateConflictError):
        state_store.complete_turn(turn.id, "not allowed")


def test_resource_refs_are_opaque_deduplicated_and_ordered(state_store) -> None:
    conversation = state_store.create_conversation()
    turn = state_store.create_turn(conversation.id, "refs")
    refs = ("opaque:anything", "pdi:resource:not-parsed", "opaque:anything")
    state_store.complete_turn(turn.id, "done", refs)
    assistant = state_store.get_conversation(conversation.id).messages[-1]
    assert [(item.resource_ref, item.ordinal) for item in assistant.resource_refs] == [("opaque:anything", 0), ("pdi:resource:not-parsed", 1)]


def test_completion_transaction_rolls_back_on_assistant_insert_failure(state_store) -> None:
    conversation = state_store.create_conversation()
    turn = state_store.create_turn(conversation.id, "hello")

    def fail_assistant(mapper, connection, target) -> None:
        if target.role == "assistant":
            raise RuntimeError("synthetic persistence failure")

    event.listen(Message, "before_insert", fail_assistant)
    try:
        with pytest.raises(RuntimeError, match="synthetic persistence failure"):
            state_store.complete_turn(turn.id, "partial must not persist")
    finally:
        event.remove(Message, "before_insert", fail_assistant)

    assert state_store.get_turn(turn.id).status == "running"
    assert [(message.role, message.body) for message in state_store.get_conversation(conversation.id).messages] == [("user", "hello")]


def test_startup_reconciliation_interrupts_only_running_turns(state_store) -> None:
    conversation = state_store.create_conversation()
    orphan = state_store.create_turn(conversation.id, "orphan")
    assert state_store.interrupt_orphaned_running_turns() == 1
    reconciled = state_store.get_turn(orphan.id)
    assert reconciled.status == "interrupted"
    assert reconciled.assistant_message_id is None
    assert state_store.interrupt_orphaned_running_turns() == 0
