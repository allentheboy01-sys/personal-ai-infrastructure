from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


class ResourceType(StrEnum):
    FILE = "file"
    MESSAGE = "message"


@dataclass
class Asset:
    id: str = field(default_factory=lambda: str(uuid4()))
    resource_type: ResourceType = ResourceType.FILE
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.resource_type = ResourceType(self.resource_type)
