from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ResourcePersonRelationORM(Base):
    __tablename__ = "resource_person_relations"
    __table_args__ = (
        CheckConstraint(
            "btrim(provider) <> ''",
            name="ck_resource_person_relations_provider_nonempty",
        ),
    )

    resource_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "assets.id",
            ondelete="RESTRICT",
            name="fk_resource_person_relations_resource",
        ),
        primary_key=True,
    )
    person_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "persons.id",
            ondelete="RESTRICT",
            name="fk_resource_person_relations_person",
        ),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    inactive_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
