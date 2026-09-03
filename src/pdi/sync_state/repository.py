from abc import ABC, abstractmethod
from datetime import UTC, datetime

from sqlalchemy import Engine, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from pdi.repository.orm.provider_sync_state import ProviderSyncStateORM

from .models import ProviderSyncState


class ProviderSyncStateRepository(ABC):
    @abstractmethod
    def get_or_create(
        self,
        provider: str,
        mechanism: str,
    ) -> ProviderSyncState:
        raise NotImplementedError

    @abstractmethod
    def read(
        self,
        provider: str,
        mechanism: str,
    ) -> ProviderSyncState | None:
        raise NotImplementedError

    @abstractmethod
    def compare_and_swap_checkpoint(
        self,
        provider: str,
        mechanism: str,
        *,
        expected_version: int,
        checkpoint: str,
    ) -> ProviderSyncState | None:
        raise NotImplementedError

    @abstractmethod
    def mark_reconciliation_required(
        self,
        provider: str,
        mechanism: str,
        *,
        expected_version: int,
    ) -> ProviderSyncState | None:
        raise NotImplementedError

    @abstractmethod
    def recover_after_reconciliation(
        self,
        provider: str,
        mechanism: str,
        *,
        expected_version: int,
        trusted_checkpoint: str,
    ) -> ProviderSyncState | None:
        """Restore trusted incremental state after proven reconciliation."""
        raise NotImplementedError


class PostgreSQLProviderSyncStateRepository(ProviderSyncStateRepository):
    def __init__(self, engine: Engine) -> None:
        self._session_factory = sessionmaker(
            bind=engine,
            class_=Session,
            expire_on_commit=False,
        )

    @staticmethod
    def _to_domain(row: ProviderSyncStateORM) -> ProviderSyncState:
        return ProviderSyncState(
            provider=row.provider,
            mechanism=row.mechanism,
            checkpoint=row.checkpoint,
            version=row.version,
            reconciliation_required=row.reconciliation_required,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def read(
        self,
        provider: str,
        mechanism: str,
    ) -> ProviderSyncState | None:
        with self._session_factory() as session:
            row = session.get(ProviderSyncStateORM, (provider, mechanism))
            return None if row is None else self._to_domain(row)

    def get_or_create(
        self,
        provider: str,
        mechanism: str,
    ) -> ProviderSyncState:
        existing = self.read(provider, mechanism)
        if existing is not None:
            return existing
        now = datetime.now(UTC)
        row = ProviderSyncStateORM(
            provider=provider,
            mechanism=mechanism,
            checkpoint=None,
            version=0,
            reconciliation_required=False,
            created_at=now,
            updated_at=now,
        )
        with self._session_factory() as session:
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                concurrent = session.get(
                    ProviderSyncStateORM,
                    (provider, mechanism),
                )
                if concurrent is None:
                    raise
                return self._to_domain(concurrent)
            return self._to_domain(row)

    def _cas(
        self,
        provider: str,
        mechanism: str,
        *,
        expected_version: int,
        values: dict[str, object],
        expected_reconciliation_required: bool | None = None,
    ) -> ProviderSyncState | None:
        with self._session_factory() as session:
            statement = update(ProviderSyncStateORM).where(
                ProviderSyncStateORM.provider == provider,
                ProviderSyncStateORM.mechanism == mechanism,
                ProviderSyncStateORM.version == expected_version,
            )
            if expected_reconciliation_required is not None:
                statement = statement.where(
                    ProviderSyncStateORM.reconciliation_required
                    == expected_reconciliation_required
                )
            row = session.execute(
                statement
                .values(
                    **values,
                    version=expected_version + 1,
                    updated_at=datetime.now(UTC),
                )
                .returning(ProviderSyncStateORM)
            ).scalar_one_or_none()
            if row is None:
                session.rollback()
                return None
            session.commit()
            return self._to_domain(row)

    def compare_and_swap_checkpoint(
        self,
        provider: str,
        mechanism: str,
        *,
        expected_version: int,
        checkpoint: str,
    ) -> ProviderSyncState | None:
        self._validate_trusted_checkpoint(checkpoint)
        return self._cas(
            provider,
            mechanism,
            expected_version=expected_version,
            values={"checkpoint": checkpoint},
            expected_reconciliation_required=False,
        )

    def mark_reconciliation_required(
        self,
        provider: str,
        mechanism: str,
        *,
        expected_version: int,
    ) -> ProviderSyncState | None:
        return self._cas(
            provider,
            mechanism,
            expected_version=expected_version,
            values={"reconciliation_required": True},
        )

    def recover_after_reconciliation(
        self,
        provider: str,
        mechanism: str,
        *,
        expected_version: int,
        trusted_checkpoint: str,
    ) -> ProviderSyncState | None:
        self._validate_trusted_checkpoint(trusted_checkpoint)
        return self._cas(
            provider,
            mechanism,
            expected_version=expected_version,
            values={
                "checkpoint": trusted_checkpoint,
                "reconciliation_required": False,
            },
            expected_reconciliation_required=True,
        )

    @staticmethod
    def _validate_trusted_checkpoint(checkpoint: str) -> None:
        if not isinstance(checkpoint, str) or not checkpoint:
            raise ValueError("A trusted checkpoint must be a non-empty string")
