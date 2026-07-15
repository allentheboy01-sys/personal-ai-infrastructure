from uuid import UUID

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from repository.orm.base import Base


class AssetSourceORM(Base):
    __tablename__ = "asset_sources"

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_id",
            name="uq_asset_sources_provider_external_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )

    blob_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "blobs.id",
            ondelete="RESTRICT",
            name="fk_asset_sources_blob",
        ),
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    external_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    name: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    version_tag: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )