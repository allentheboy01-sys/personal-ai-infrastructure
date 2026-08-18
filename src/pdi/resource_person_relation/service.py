from typing import Protocol

from .models import ProviderRelationInventory, RelationSyncResult
from .repository import ResourcePersonRelationRepository


class RelationInventoryAdapter(Protocol):
    provider: str

    def connect(self) -> None: ...
    def scan(
        self, person_external_ids: tuple[str, ...]
    ) -> ProviderRelationInventory: ...


class ResourcePersonRelationSyncService:
    def __init__(
        self,
        adapter: RelationInventoryAdapter,
        repository: ResourcePersonRelationRepository,
    ) -> None:
        self._adapter = adapter
        self._repository = repository

    def sync_once(self) -> RelationSyncResult:
        self._adapter.connect()
        identities = self._repository.list_active_person_external_ids(
            self._adapter.provider
        )
        inventory = self._adapter.scan(identities)
        if inventory.provider != self._adapter.provider:
            raise ValueError("relation inventory provider mismatch")
        return self._repository.reconcile_provider_relations(
            inventory.provider, inventory.pairs
        )
