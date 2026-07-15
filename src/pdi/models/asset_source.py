from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class AssetSource:
    id: str = field(default_factory=lambda: str(uuid4()))
    blob_id: str | None = None
    provider: str = "unknown"
    external_id: str | None = None
    path: str | None = None
    name: str | None = None
    version_tag: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)