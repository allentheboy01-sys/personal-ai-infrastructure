import re
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from .models import Conversation, Message, MessageResourceRef, Turn


class NotFoundError(Exception):
    pass


class ActiveTurnError(Exception):
    pass


class StateConflictError(Exception):
    pass


_ERROR_CODE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})
MAX_MESSAGE_RESOURCE_REFS = 8


class JarvisStateStore:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def create_conversation(self, title: str = "New conversation") -> Conversation:
        clean_title = title.strip()[:200] or "New conversation"
        with self._sessions.begin() as session:
            conversation = Conversation(title=clean_title)
            session.add(conversation)
        return conversation

    def list_conversations(self) -> list[Conversation]:
        with self._sessions() as session:
            return list(session.scalars(select(Conversation).order_by(Conversation.updated_at.desc())))

    def get_conversation(self, conversation_id: UUID) -> Conversation:
        with self._sessions() as session:
            conversation = session.scalar(select(Conversation).where(Conversation.id == conversation_id).options(selectinload(Conversation.messages).selectinload(Message.resource_refs)))
            if conversation is None:
                raise NotFoundError("conversation_not_found")
            return conversation

    def create_turn(self, conversation_id: UUID, body: str) -> Turn:
        clean_body = body.strip()
        if not clean_body:
            raise ValueError("message body must not be empty")
        try:
            with self._sessions.begin() as session:
                conversation = session.get(Conversation, conversation_id)
                if conversation is None:
                    raise NotFoundError("conversation_not_found")
                active = session.scalar(select(Turn.id).where(Turn.conversation_id == conversation_id, Turn.status == "running"))
                if active is not None:
                    raise ActiveTurnError("conversation_has_active_turn")
                now = datetime.now(UTC)
                message = Message(conversation_id=conversation_id, role="user", body=clean_body, created_at=now)
                session.add(message)
                session.flush()
                turn = Turn(conversation_id=conversation_id, user_message_id=message.id, status="running", started_at=now)
                session.add(turn)
                conversation.updated_at = now
            return turn
        except IntegrityError as error:
            raise ActiveTurnError("conversation_has_active_turn") from error

    def get_turn(self, turn_id: UUID) -> Turn:
        with self._sessions() as session:
            turn = session.get(Turn, turn_id)
            if turn is None:
                raise NotFoundError("turn_not_found")
            return turn

    def history_for_turn(self, turn_id: UUID) -> tuple[Message, ...]:
        turn = self.get_turn(turn_id)
        conversation = self.get_conversation(turn.conversation_id)
        return tuple(message for message in conversation.messages if message.created_at <= turn.started_at)

    def complete_turn(self, turn_id: UUID, assistant_body: str, resource_refs: Sequence[str] = ()) -> Turn:
        unique_refs = tuple(dict.fromkeys(resource_refs))
        if len(unique_refs) > MAX_MESSAGE_RESOURCE_REFS:
            raise ValueError("too many message resource refs")
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            turn = session.get(Turn, turn_id)
            if turn is None:
                raise NotFoundError("turn_not_found")
            if turn.status != "running":
                raise StateConflictError("turn_not_running")
            message = Message(conversation_id=turn.conversation_id, role="assistant", body=assistant_body, created_at=now)
            session.add(message)
            session.flush()
            for ordinal, resource_ref in enumerate(unique_refs):
                session.add(MessageResourceRef(message_id=message.id, resource_ref=resource_ref, ordinal=ordinal))
            turn.assistant_message_id = message.id
            turn.status = "completed"
            turn.completed_at = now
            conversation = session.get(Conversation, turn.conversation_id)
            assert conversation is not None
            conversation.updated_at = now
        return turn

    def finish_without_message(self, turn_id: UUID, status: str, error_code: str | None = None) -> Turn:
        if status not in {"failed", "cancelled", "interrupted"}:
            raise ValueError("invalid terminal status")
        if error_code is not None and not _ERROR_CODE.fullmatch(error_code):
            raise ValueError("invalid error code")
        with self._sessions.begin() as session:
            turn = session.get(Turn, turn_id)
            if turn is None:
                raise NotFoundError("turn_not_found")
            if turn.status in _TERMINAL:
                return turn
            if turn.status != "running":
                raise StateConflictError("turn_not_running")
            turn.status = status
            turn.error_code = error_code
            turn.completed_at = datetime.now(UTC)
        return turn

    def interrupt_orphaned_running_turns(self) -> int:
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            result = session.execute(update(Turn).where(Turn.status == "running").values(status="interrupted", completed_at=now, error_code="process_restarted"))
            return result.rowcount
