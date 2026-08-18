from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PersonORM(Base):
    __tablename__ = "persons"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class PersonSourceORM(Base):
    __tablename__ = "person_sources"
    __table_args__ = (
        CheckConstraint(
            "btrim(provider) <> ''",
            name="ck_person_sources_provider_nonempty",
        ),
        CheckConstraint(
            "btrim(external_id) <> ''",
            name="ck_person_sources_external_id_nonempty",
        ),
    )

    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    external_id: Mapped[str] = mapped_column(Text, primary_key=True)
    person_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "persons.id",
            ondelete="RESTRICT",
            name="fk_person_sources_person",
        ),
        nullable=False,
    )
    inactive_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
