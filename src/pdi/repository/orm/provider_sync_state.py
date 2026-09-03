from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ProviderSyncStateORM(Base):
    __tablename__ = "provider_sync_state"
    __table_args__ = (
        CheckConstraint(
            "btrim(provider) <> ''",
            name="ck_provider_sync_state_provider_nonempty",
        ),
        CheckConstraint(
            "btrim(mechanism) <> ''",
            name="ck_provider_sync_state_mechanism_nonempty",
        ),
        CheckConstraint(
            "version >= 0",
            name="ck_provider_sync_state_version_nonnegative",
        ),
    )

    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    mechanism: Mapped[str] = mapped_column(Text, primary_key=True)
    checkpoint: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reconciliation_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
