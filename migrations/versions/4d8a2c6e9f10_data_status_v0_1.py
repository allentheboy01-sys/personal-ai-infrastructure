"""Add Data Status V0.1 pipeline run ledger.

Revision ID: 4d8a2c6e9f10
Revises: 8f3a1d2c4b5e
Create Date: 2026-08-18
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "4d8a2c6e9f10"
down_revision: str | Sequence[str] | None = "8f3a1d2c4b5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pipeline_key", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "btrim(pipeline_key) <> ''",
            name="ck_pipeline_runs_key_nonempty",
        ),
        sa.CheckConstraint(
            "kind IN ('provider_sync', 'enrichment')",
            name="ck_pipeline_runs_kind",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_pipeline_runs_status",
        ),
        sa.CheckConstraint(
            "(status = 'running' AND finished_at IS NULL AND error_code IS NULL) OR "
            "(status = 'completed' AND finished_at IS NOT NULL AND error_code IS NULL) OR "
            "(status = 'failed' AND finished_at IS NOT NULL AND error_code IS NOT NULL)",
            name="ck_pipeline_runs_lifecycle",
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR error_code IN "
            "('execution_failed', 'interrupted_previous_run')",
            name="ck_pipeline_runs_error_code",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pipeline_runs_key_started_at",
        "pipeline_runs",
        ["pipeline_key", sa.text("started_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_pipeline_runs_running_key",
        "pipeline_runs",
        ["pipeline_key"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_pipeline_runs_running_key", table_name="pipeline_runs"
    )
    op.drop_index(
        "ix_pipeline_runs_key_started_at", table_name="pipeline_runs"
    )
    op.drop_table("pipeline_runs")
