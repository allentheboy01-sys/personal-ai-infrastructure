"""Add Query V0.2 pagination and active-source indexes.

Revision ID: 1c7b2f9e4a6d
Revises: 7452797c95ca
Create Date: 2026-08-12

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "1c7b2f9e4a6d"
down_revision: str | Sequence[str] | None = "7452797c95ca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_assets_created_at_id",
        "assets",
        [
            sa.text("created_at DESC"),
            sa.text("id ASC"),
        ],
        unique=False,
    )
    op.create_index(
        "ix_asset_sources_active_blob_id",
        "asset_sources",
        ["blob_id"],
        unique=False,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_asset_sources_active_blob_id",
        table_name="asset_sources",
    )
    op.drop_index(
        "ix_assets_created_at_id",
        table_name="assets",
    )
