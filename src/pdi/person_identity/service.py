from typing import Protocol

from .models import EnumerablePersonInventory, PersonSyncResult
from .repository import PersonRepository


class EnumerablePeopleAdapter(Protocol):
    def connect(self) -> None: ...
    def scan(self) -> EnumerablePersonInventory: ...


class PersonSyncService:
    def __init__(
        self,
        adapter: EnumerablePeopleAdapter,
        repository: PersonRepository,
    ) -> None:
        self._adapter = adapter
        self._repository = repository

    def sync_once(self) -> PersonSyncResult:
        self._adapter.connect()
        inventory = self._adapter.scan()
        return self._repository.reconcile_inventory(
            inventory.provider,
            inventory.identities,
        )
