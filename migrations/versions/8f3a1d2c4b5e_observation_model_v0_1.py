"""Add Observation Model V0.1 tables.

Revision ID: 8f3a1d2c4b5e
Revises: 1c7b2f9e4a6d
Create Date: 2026-08-13
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "8f3a1d2c4b5e"
down_revision: str | Sequence[str] | None = "1c7b2f9e4a6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resource_statements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("predicate", sa.Text(), nullable=False),
        sa.Column("value_type", sa.Text(), nullable=False),
        sa.Column("string_value", sa.Text(), nullable=True),
        sa.Column("integer_value", sa.BigInteger(), nullable=True),
        sa.Column("float_value", sa.Float(), nullable=True),
        sa.Column("boolean_value", sa.Boolean(), nullable=True),
        sa.Column("datetime_value", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resource_value_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generator_type", sa.Text(), nullable=False),
        sa.Column("generator_name", sa.Text(), nullable=False),
        sa.Column("generator_version", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_locator", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("btrim(predicate) <> ''", name="ck_resource_statements_predicate_nonempty"),
        sa.CheckConstraint("btrim(generator_type) <> ''", name="ck_resource_statements_generator_type_nonempty"),
        sa.CheckConstraint("btrim(generator_name) <> ''", name="ck_resource_statements_generator_name_nonempty"),
        sa.CheckConstraint("btrim(generator_version) <> ''", name="ck_resource_statements_generator_version_nonempty"),
        sa.CheckConstraint("btrim(source_kind) <> ''", name="ck_resource_statements_source_kind_nonempty"),
        sa.CheckConstraint("btrim(source_locator) <> ''", name="ck_resource_statements_source_locator_nonempty"),
        sa.CheckConstraint("value_type IN ('string', 'integer', 'float', 'boolean', 'datetime', 'resource_ref')", name="ck_resource_statements_value_type"),
        sa.CheckConstraint("source_kind IN ('provider_metadata', 'resource_content')", name="ck_resource_statements_source_kind"),
        sa.CheckConstraint("confidence IS NULL OR (confidence = confidence AND confidence >= 0 AND confidence <= 1)", name="ck_resource_statements_confidence"),
        sa.CheckConstraint("num_nonnulls(string_value, integer_value, float_value, boolean_value, datetime_value, resource_value_asset_id) = 1", name="ck_resource_statements_exactly_one_value"),
        sa.CheckConstraint("(value_type = 'string' AND string_value IS NOT NULL) OR (value_type = 'integer' AND integer_value IS NOT NULL) OR (value_type = 'float' AND float_value IS NOT NULL) OR (value_type = 'boolean' AND boolean_value IS NOT NULL) OR (value_type = 'datetime' AND datetime_value IS NOT NULL) OR (value_type = 'resource_ref' AND resource_value_asset_id IS NOT NULL)", name="ck_resource_statements_value_discriminator"),
        sa.ForeignKeyConstraint(["subject_asset_id"], ["assets.id"], name="fk_resource_statements_subject_asset", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resource_value_asset_id"], ["assets.id"], name="fk_resource_statements_resource_value_asset", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resource_statements_current_subject_predicate", "resource_statements", ["subject_asset_id", "predicate"], unique=False, postgresql_where=sa.text("is_current"))
    op.create_index("ix_resource_statements_current_generator", "resource_statements", ["subject_asset_id", "predicate", "generator_type", "generator_name", "generator_version"], unique=False, postgresql_where=sa.text("is_current"))
    op.create_index("ix_resource_statements_subject_history", "resource_statements", ["subject_asset_id", sa.text("created_at DESC"), sa.text("id ASC")], unique=False)

    op.create_table(
        "resource_enrichments",
        sa.Column("subject_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("extractor_type", sa.Text(), nullable=False),
        sa.Column("extractor_name", sa.Text(), nullable=False),
        sa.Column("extractor_version", sa.Text(), nullable=False),
        sa.Column("input_fingerprint", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint("btrim(extractor_type) <> ''", name="ck_resource_enrichments_type_nonempty"),
        sa.CheckConstraint("btrim(extractor_name) <> ''", name="ck_resource_enrichments_name_nonempty"),
        sa.CheckConstraint("btrim(extractor_version) <> ''", name="ck_resource_enrichments_version_nonempty"),
        sa.CheckConstraint("btrim(input_fingerprint) <> ''", name="ck_resource_enrichments_fingerprint_nonempty"),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_resource_enrichments_status"),
        sa.ForeignKeyConstraint(["subject_asset_id"], ["assets.id"], name="fk_resource_enrichments_subject_asset", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("subject_asset_id", "extractor_type", "extractor_name", "extractor_version", name="pk_resource_enrichments"),
    )


def downgrade() -> None:
    op.drop_table("resource_enrichments")
    op.drop_index("ix_resource_statements_subject_history", table_name="resource_statements")
    op.drop_index("ix_resource_statements_current_generator", table_name="resource_statements")
    op.drop_index("ix_resource_statements_current_subject_predicate", table_name="resource_statements")
    op.drop_table("resource_statements")
