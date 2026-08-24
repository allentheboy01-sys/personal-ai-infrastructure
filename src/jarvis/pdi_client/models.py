from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ResourceType = Literal["file", "message"]
PresentationKind = Literal["image", "video", "document", "message", "generic"]
ProviderState = Literal["not_synced", "syncing", "processing", "ready", "attention"]


@dataclass(frozen=True, slots=True)
class ResourceCapabilities:
    detail: bool
    preview: bool
    open: bool
    playback: bool = False


@dataclass(frozen=True, slots=True)
class ResourceSummary:
    resource_ref: str
    resource_type: ResourceType
    title: str
    secondary_text: str | None
    timestamp: str | None
    presentation_kind: PresentationKind
    presentation_label: str
    providers: tuple[str, ...]
    capabilities: ResourceCapabilities


@dataclass(frozen=True, slots=True)
class ResourceDetail:
    summary: ResourceSummary
    facts: tuple[tuple[str, str], ...]
    mime_type: str | None
    size_bytes: int | None
    notice: str | None = None


@dataclass(frozen=True, slots=True)
class ResourcePage:
    resources: tuple[ResourceSummary, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class ProviderSummary:
    provider_ref: str
    provider_type: str
    display_name: str
    category: str
    configured: bool
    access_mode: Literal["read_only", "read_write", "unknown"]
    resource_count: int
    operational_state: ProviderState
    last_success_at: str | None


@dataclass(frozen=True, slots=True)
class ProviderDetail:
    summary: ProviderSummary
    description: str
    capabilities: tuple[str, ...]
    stages: tuple[tuple[str, Literal["completed", "current", "pending", "attention"]], ...]
