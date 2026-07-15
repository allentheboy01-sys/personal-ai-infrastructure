from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from repository.orm.base import Base


class BlobORM(Base):
    __tablename__ = "blobs"

    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "hash",
            name="uq_blobs_asset_hash",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )

    asset_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "assets.id",
            ondelete="RESTRICT",
            name="fk_blobs_asset",
        ),
        nullable=False,
    )

    hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        index=True,
    )

    size: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    mime_type: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )