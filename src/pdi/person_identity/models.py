from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID


def utc_instant(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("person identity timestamp must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class Person:
    id: UUID
    created_at: datetime


@dataclass(frozen=True)
class PersonSource:
    provider: str
    external_id: str
    person_id: UUID
    inactive_at: datetime | None


@dataclass(frozen=True)
class EnumerablePersonInventory:
    provider: str
    external_ids: tuple[str, ...]
    reported_total: int


@dataclass(frozen=True)
class PersonSyncResult:
    discovered: int
    created: int
    existing: int
    reactivated: int
    inactivated: int
