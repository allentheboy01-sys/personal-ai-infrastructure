from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ProviderSyncState:
    provider: str
    mechanism: str
    checkpoint: str | None
    version: int
    reconciliation_required: bool
    created_at: datetime
    updated_at: datetime
