"""Add PDI-owned Provider incremental sync state.

Revision ID: 5e7a9c2d1f30
Revises: 2f6a8c1d4e90
Create Date: 2026-09-03
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "5e7a9c2d1f30"
down_revision: str | Sequence[str] | None = "2f6a8c1d4e90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_sync_state",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("mechanism", sa.Text(), nullable=False),
        sa.Column("checkpoint", sa.Text(), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column(
            "reconciliation_required",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(provider) <> ''",
            name="ck_provider_sync_state_provider_nonempty",
        ),
        sa.CheckConstraint(
            "btrim(mechanism) <> ''",
            name="ck_provider_sync_state_mechanism_nonempty",
        ),
        sa.CheckConstraint(
            "version >= 0",
            name="ck_provider_sync_state_version_nonnegative",
        ),
        sa.PrimaryKeyConstraint(
            "provider",
            "mechanism",
            name="pk_provider_sync_state",
        ),
    )


def downgrade() -> None:
    op.drop_table("provider_sync_state")
