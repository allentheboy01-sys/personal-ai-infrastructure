from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                key: _freeze_value(nested_value)
                for key, nested_value in value.items()
            }
        )

    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_value(item)
            for item in value
        )

    return value


def _freeze_metadata(
    metadata: Mapping[str, Any],
) -> Mapping[str, Any]:
    return _freeze_value(metadata)


@dataclass(frozen=True, slots=True)
class AssetSummary:
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class BlobView:
    id: str
    asset_id: str
    hash: str
    size: int | None
    mime_type: str | None


@dataclass(frozen=True, slots=True)
class SourceView:
    id: str
    blob_id: str
    provider: str
    external_id: str
    path: str | None
    name: str | None
    version_tag: str | None
    metadata: Mapping[str, Any]
    is_active: bool
    deleted_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metadata",
            _freeze_metadata(self.metadata),
        )


@dataclass(frozen=True, slots=True)
class AssetDetail:
    id: str
    title: str
    metadata: Mapping[str, Any]
    created_at: datetime
    updated_at: datetime
    blobs: tuple[BlobView, ...]
    sources: tuple[SourceView, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metadata",
            _freeze_metadata(self.metadata),
        )
        object.__setattr__(
            self,
            "blobs",
            tuple(self.blobs),
        )
        object.__setattr__(
            self,
            "sources",
            tuple(self.sources),
        )
