"""Add provider-derived Person labels and retrieval indexes.

Revision ID: 7d2f4a6b8c10
Revises: 3b1e6f8a4c20
Create Date: 2026-08-23
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "7d2f4a6b8c10"
down_revision: str | Sequence[str] | None = "3b1e6f8a4c20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "person_sources",
        sa.Column("display_name", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_person_sources_display_name_nonempty",
        "person_sources",
        "display_name IS NULL OR btrim(display_name) <> ''",
    )
    op.create_index(
        "ix_person_sources_active_display_name",
        "person_sources",
        [sa.text("lower(display_name)"), "person_id"],
        unique=False,
        postgresql_where=sa.text(
            "inactive_at IS NULL AND display_name IS NOT NULL"
        ),
    )
    op.create_index(
        "ix_resource_person_relations_active_person_resource",
        "resource_person_relations",
        ["person_id", "resource_id"],
        unique=False,
        postgresql_where=sa.text("inactive_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_resource_person_relations_active_person_resource",
        table_name="resource_person_relations",
    )
    op.drop_index(
        "ix_person_sources_active_display_name",
        table_name="person_sources",
    )
    op.drop_constraint(
        "ck_person_sources_display_name_nonempty",
        "person_sources",
        type_="check",
    )
    op.drop_column("person_sources", "display_name")
