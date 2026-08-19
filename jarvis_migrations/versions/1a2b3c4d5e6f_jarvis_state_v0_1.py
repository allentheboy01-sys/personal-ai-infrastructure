"""Jarvis state V0.1.

Revision ID: 1a2b3c4d5e6f
Revises:
"""
from alembic import op
import sqlalchemy as sa


revision = "1a2b3c4d5e6f"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jarvis_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "jarvis_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_jarvis_message_role"),
        sa.ForeignKeyConstraint(["conversation_id"], ["jarvis_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jarvis_messages_conversation_id", "jarvis_messages", ["conversation_id"])
    op.create_table(
        "jarvis_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_message_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_message_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed', 'cancelled', 'interrupted')", name="ck_jarvis_turn_status"),
        sa.ForeignKeyConstraint(["assistant_message_id"], ["jarvis_messages.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["conversation_id"], ["jarvis_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_message_id"], ["jarvis_messages.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assistant_message_id"),
        sa.UniqueConstraint("user_message_id"),
    )
    op.create_index("ix_jarvis_turns_conversation_id", "jarvis_turns", ["conversation_id"])
    op.create_index("uq_jarvis_running_turn_per_conversation", "jarvis_turns", ["conversation_id"], unique=True, postgresql_where=sa.text("status = 'running'"))
    op.create_table(
        "jarvis_message_resource_refs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("resource_ref", sa.String(300), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ordinal >= 0", name="ck_jarvis_resource_ordinal"),
        sa.ForeignKeyConstraint(["message_id"], ["jarvis_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "ordinal", name="uq_jarvis_message_resource_ordinal"),
        sa.UniqueConstraint("message_id", "resource_ref", name="uq_jarvis_message_resource_ref"),
    )
    op.create_index("ix_jarvis_message_resource_refs_message_id", "jarvis_message_resource_refs", ["message_id"])


def downgrade() -> None:
    op.drop_table("jarvis_message_resource_refs")
    op.drop_table("jarvis_turns")
    op.drop_table("jarvis_messages")
    op.drop_table("jarvis_conversations")
