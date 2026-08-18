from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderRelationInventory:
    provider: str
    pairs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class RelationSyncResult:
    observed: int
    created: int
    unchanged: int
    reactivated: int
    inactivated: int
    skipped_unmapped: int
