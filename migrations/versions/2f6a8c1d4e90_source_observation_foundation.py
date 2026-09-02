"""Add normalized Source content observations.

Revision ID: 2f6a8c1d4e90
Revises: 7d2f4a6b8c10
Create Date: 2026-09-02
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "2f6a8c1d4e90"
down_revision: str | Sequence[str] | None = "7d2f4a6b8c10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "asset_sources",
        sa.Column("provider_mime_type", sa.Text(), nullable=True),
    )
    op.add_column(
        "asset_sources",
        sa.Column("provider_size", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("asset_sources", "provider_size")
    op.drop_column("asset_sources", "provider_mime_type")
