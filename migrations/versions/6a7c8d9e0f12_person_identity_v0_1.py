"""Add minimal Person Identity V0.1 tables.

Revision ID: 6a7c8d9e0f12
Revises: 4d8a2c6e9f10
Create Date: 2026-08-18
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "6a7c8d9e0f12"
down_revision: str | Sequence[str] | None = "4d8a2c6e9f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "persons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "person_sources",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inactive_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "btrim(external_id) <> ''",
            name="ck_person_sources_external_id_nonempty",
        ),
        sa.CheckConstraint(
            "btrim(provider) <> ''",
            name="ck_person_sources_provider_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["persons.id"],
            name="fk_person_sources_person",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("provider", "external_id"),
    )


def downgrade() -> None:
    op.drop_table("person_sources")
    op.drop_table("persons")
