from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "jarvis_conversations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.created_at")
    turns: Mapped[list["Turn"]] = relationship(back_populates="conversation")


class Message(Base):
    __tablename__ = "jarvis_messages"
    __table_args__ = (CheckConstraint("role IN ('user', 'assistant')", name="ck_jarvis_message_role"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("jarvis_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    resource_refs: Mapped[list["MessageResourceRef"]] = relationship(back_populates="message", order_by="MessageResourceRef.ordinal", cascade="all, delete-orphan")


class Turn(Base):
    __tablename__ = "jarvis_turns"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'completed', 'failed', 'cancelled', 'interrupted')", name="ck_jarvis_turn_status"),
        Index("uq_jarvis_running_turn_per_conversation", "conversation_id", unique=True, postgresql_where=text("status = 'running'"), sqlite_where=text("status = 'running'")),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("jarvis_conversations.id", ondelete="CASCADE"), index=True)
    user_message_id: Mapped[UUID] = mapped_column(ForeignKey("jarvis_messages.id", ondelete="RESTRICT"), unique=True)
    assistant_message_id: Mapped[UUID | None] = mapped_column(ForeignKey("jarvis_messages.id", ondelete="RESTRICT"), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))

    conversation: Mapped[Conversation] = relationship(back_populates="turns")
    user_message: Mapped[Message] = relationship(foreign_keys=[user_message_id])
    assistant_message: Mapped[Message | None] = relationship(foreign_keys=[assistant_message_id])


class MessageResourceRef(Base):
    __tablename__ = "jarvis_message_resource_refs"
    __table_args__ = (
        UniqueConstraint("message_id", "resource_ref", name="uq_jarvis_message_resource_ref"),
        UniqueConstraint("message_id", "ordinal", name="uq_jarvis_message_resource_ordinal"),
        CheckConstraint("ordinal >= 0", name="ck_jarvis_resource_ordinal"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    message_id: Mapped[UUID] = mapped_column(ForeignKey("jarvis_messages.id", ondelete="CASCADE"), index=True)
    resource_ref: Mapped[str] = mapped_column(String(300))
    ordinal: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    message: Mapped[Message] = relationship(back_populates="resource_refs")
