"""Add Typed Resource V0.1 discriminator.

Revision ID: 3b1e6f8a4c20
Revises: 9c4e1a7b2d30
Create Date: 2026-08-18
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "3b1e6f8a4c20"
down_revision: str | Sequence[str] | None = "9c4e1a7b2d30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column(
            "resource_type",
            sa.Text(),
            nullable=False,
            server_default="file",
        ),
    )
    op.create_check_constraint(
        "ck_assets_resource_type",
        "assets",
        "resource_type IN ('file', 'message')",
    )
    op.alter_column(
        "assets",
        "resource_type",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_assets_resource_type",
        "assets",
        type_="check",
    )
    op.drop_column("assets", "resource_type")
