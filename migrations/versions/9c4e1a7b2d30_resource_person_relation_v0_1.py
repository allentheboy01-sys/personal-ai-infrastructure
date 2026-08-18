"""Add Resource-Person Relation V0.1 table.

Revision ID: 9c4e1a7b2d30
Revises: 6a7c8d9e0f12
Create Date: 2026-08-18
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "9c4e1a7b2d30"
down_revision: str | Sequence[str] | None = "6a7c8d9e0f12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resource_person_relations",
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("inactive_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "btrim(provider) <> ''",
            name="ck_resource_person_relations_provider_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["persons.id"],
            name="fk_resource_person_relations_person", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"], ["assets.id"],
            name="fk_resource_person_relations_resource", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("resource_id", "person_id", "provider"),
    )


def downgrade() -> None:
    op.drop_table("resource_person_relations")
