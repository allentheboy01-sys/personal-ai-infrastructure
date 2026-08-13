from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    Text,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pdi.repository.orm.base import Base


class ResourceStatementORM(Base):
    __tablename__ = "resource_statements"
    __table_args__ = (
        CheckConstraint("btrim(predicate) <> ''", name="ck_resource_statements_predicate_nonempty"),
        CheckConstraint("btrim(generator_type) <> ''", name="ck_resource_statements_generator_type_nonempty"),
        CheckConstraint("btrim(generator_name) <> ''", name="ck_resource_statements_generator_name_nonempty"),
        CheckConstraint("btrim(generator_version) <> ''", name="ck_resource_statements_generator_version_nonempty"),
        CheckConstraint("btrim(source_kind) <> ''", name="ck_resource_statements_source_kind_nonempty"),
        CheckConstraint("btrim(source_locator) <> ''", name="ck_resource_statements_source_locator_nonempty"),
        CheckConstraint(
            "value_type IN ('string', 'integer', 'float', 'boolean', 'datetime', 'resource_ref')",
            name="ck_resource_statements_value_type",
        ),
        CheckConstraint(
            "source_kind IN ('provider_metadata', 'resource_content')",
            name="ck_resource_statements_source_kind",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence = confidence AND confidence >= 0 AND confidence <= 1)",
            name="ck_resource_statements_confidence",
        ),
        CheckConstraint(
            "num_nonnulls(string_value, integer_value, float_value, boolean_value, datetime_value, resource_value_asset_id) = 1",
            name="ck_resource_statements_exactly_one_value",
        ),
        CheckConstraint(
            "(value_type = 'string' AND string_value IS NOT NULL) OR "
            "(value_type = 'integer' AND integer_value IS NOT NULL) OR "
            "(value_type = 'float' AND float_value IS NOT NULL) OR "
            "(value_type = 'boolean' AND boolean_value IS NOT NULL) OR "
            "(value_type = 'datetime' AND datetime_value IS NOT NULL) OR "
            "(value_type = 'resource_ref' AND resource_value_asset_id IS NOT NULL)",
            name="ck_resource_statements_value_discriminator",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    subject_asset_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="RESTRICT", name="fk_resource_statements_subject_asset"),
        nullable=False,
    )
    predicate: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    string_value: Mapped[str | None] = mapped_column(Text)
    integer_value: Mapped[int | None] = mapped_column(BigInteger)
    float_value: Mapped[float | None] = mapped_column(Float)
    boolean_value: Mapped[bool | None] = mapped_column(Boolean)
    datetime_value: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resource_value_asset_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="RESTRICT", name="fk_resource_statements_resource_value_asset"),
    )
    generator_type: Mapped[str] = mapped_column(Text, nullable=False)
    generator_name: Mapped[str] = mapped_column(Text, nullable=False)
    generator_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_locator: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())


Index(
    "ix_resource_statements_current_subject_predicate",
    ResourceStatementORM.subject_asset_id,
    ResourceStatementORM.predicate,
    postgresql_where=ResourceStatementORM.is_current.is_(True),
)
Index(
    "ix_resource_statements_current_generator",
    ResourceStatementORM.subject_asset_id,
    ResourceStatementORM.predicate,
    ResourceStatementORM.generator_type,
    ResourceStatementORM.generator_name,
    ResourceStatementORM.generator_version,
    postgresql_where=ResourceStatementORM.is_current.is_(True),
)
Index(
    "ix_resource_statements_subject_history",
    ResourceStatementORM.subject_asset_id,
    ResourceStatementORM.created_at.desc(),
    ResourceStatementORM.id.asc(),
)


class ResourceEnrichmentORM(Base):
    __tablename__ = "resource_enrichments"
    __table_args__ = (
        PrimaryKeyConstraint(
            "subject_asset_id", "extractor_type", "extractor_name", "extractor_version",
            name="pk_resource_enrichments",
        ),
        CheckConstraint("btrim(extractor_type) <> ''", name="ck_resource_enrichments_type_nonempty"),
        CheckConstraint("btrim(extractor_name) <> ''", name="ck_resource_enrichments_name_nonempty"),
        CheckConstraint("btrim(extractor_version) <> ''", name="ck_resource_enrichments_version_nonempty"),
        CheckConstraint("btrim(input_fingerprint) <> ''", name="ck_resource_enrichments_fingerprint_nonempty"),
        CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_resource_enrichments_status"),
    )

    subject_asset_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="RESTRICT", name="fk_resource_enrichments_subject_asset"),
        nullable=False,
    )
    extractor_type: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_name: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
