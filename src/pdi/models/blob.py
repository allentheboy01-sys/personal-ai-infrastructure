from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class Blob:
    id: str = field(default_factory=lambda: str(uuid4()))
    asset_id: str | None = None
    hash: str | None = None
    size: int | None = None
    mime_type: str | None = None