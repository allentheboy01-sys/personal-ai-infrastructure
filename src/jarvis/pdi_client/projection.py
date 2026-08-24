from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from .contract import PDIContractError, PDIProviderNotFound, PDIResourceNotFound
from .models import ProviderDetail, ProviderSummary, ResourceCapabilities, ResourceDetail, ResourcePage, ResourceSummary

PROVIDERS = {
    "immich": {"name": "Immich", "category": "Photos", "sync": "provider.immich.sync", "pipelines": ("enrichment.file_metadata", "enrichment.immich_geo", "enrichment.immich_metadata", "enrichment.immich_ocr"), "description": "Photos available to Jarvis through a read-only connection.", "capabilities": ("Browse image and video metadata", "View controlled media previews", "Use resources in agent context")},
    "nextcloud": {"name": "Nextcloud", "category": "Files", "sync": "provider.nextcloud.sync", "pipelines": ("enrichment.nextcloud_text", "enrichment.nextcloud_documents", "enrichment.file_metadata"), "description": "Files and documents available through a read-only connection.", "capabilities": ("Browse file metadata", "Search indexed documents", "Use resources in agent context")},
    "gmail": {"name": "Gmail", "category": "Messages", "sync": "provider.gmail.sync", "pipelines": ("enrichment.gmail_metadata",), "description": "Message metadata available through a manually managed, read-only connection.", "capabilities": ("Browse message metadata", "Search indexed message context", "Use metadata in agent context")},
}


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PDIContractError("pdi_invalid_response")
    return value


def _string(value: Any, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value):
        raise PDIContractError("pdi_invalid_response")
    return value


def project_resource(raw: Any, *, detail: bool = False) -> ResourceSummary | ResourceDetail:
    item = _mapping(raw)
    ref = _string(item.get("resource_ref"), required=True)
    if not ref or not ref.startswith("pdi:resource:"):
        raise PDIContractError("pdi_invalid_response")
    resource_type = _string(item.get("resource_type"), required=True)
    if resource_type not in ("file", "message"):
        raise PDIContractError("pdi_invalid_response")
    sources_raw = item.get("sources")
    if not isinstance(sources_raw, list):
        raise PDIContractError("pdi_invalid_response")
    active = [_mapping(source) for source in sources_raw if isinstance(source, Mapping) and source.get("is_active") is True]
    provider_refs = tuple(dict.fromkeys(str(source.get("provider", "")).lower() for source in active if str(source.get("provider", "")).lower() in PROVIDERS))
    providers = tuple(PROVIDERS[key]["name"] for key in provider_refs)
    if not providers:
        raise PDIContractError("pdi_invalid_response")
    variants = item.get("content_variants") if detail else None
    variants = variants if isinstance(variants, list) else []
    mime = next((source.get("mime_type") for source in active if isinstance(source.get("mime_type"), str)), None)
    if mime is None:
        mime = next((variant.get("mime_type") for variant in variants if isinstance(variant, Mapping) and isinstance(variant.get("mime_type"), str)), None)
    size = next((source.get("size_bytes") for source in active if isinstance(source.get("size_bytes"), int)), None)
    if size is None:
        size = next((variant.get("size_bytes") for variant in variants if isinstance(variant, Mapping) and isinstance(variant.get("size_bytes"), int)), None)
    if resource_type == "message":
        kind, label = "message", "Message"
    elif isinstance(mime, str) and mime.startswith("image/"):
        kind, label = "image", mime.split("/", 1)[1].upper()
    elif isinstance(mime, str) and mime.startswith("video/"):
        kind, label = "video", "Video"
    elif isinstance(mime, str) and (mime.startswith("text/") or mime == "application/pdf" or any(token in mime for token in ("document", "wordprocessing", "opendocument"))):
        kind, label = "document", _document_label(mime)
    else:
        kind, label = "generic", "File"
    preview = kind in {"image", "video"} and "immich" in provider_refs
    playback = kind == "video" and "immich" in provider_refs
    title = _string(item.get("display_name")) or ("Untitled message" if resource_type == "message" else "Untitled resource")
    timestamp = _string(item.get("pdi_first_observed_at"))
    summary = ResourceSummary(ref, resource_type, title, mime or ("Metadata only" if resource_type == "message" else None), timestamp, kind, label, providers, ResourceCapabilities(True, preview, False, playback))
    if not detail:
        return summary
    facts: list[tuple[str, str]] = [("Type", label)]
    if mime:
        facts.append(("Format", mime))
    if isinstance(size, int) and size >= 0:
        facts.append(("Size", _format_size(size)))
    if timestamp:
        facts.append(("First observed by PDI", timestamp))
    notice = "Message content is unavailable. Jarvis exposes metadata only." if resource_type == "message" else ("A browser preview is not available for this resource." if not preview else None)
    return ResourceDetail(summary, tuple(facts), mime, size, notice)


def project_resource_page(raw: Any) -> ResourcePage:
    payload = _mapping(raw)
    if payload.get("ok") is not True or not isinstance(payload.get("resources"), list):
        raise PDIContractError("pdi_invalid_response")
    return ResourcePage(tuple(project_resource(item) for item in payload["resources"]), _string(payload.get("next_cursor")))


def project_resource_detail(raw: Any) -> ResourceDetail:
    payload = _mapping(raw)
    if payload.get("ok") is not True:
        error = payload.get("error")
        if isinstance(error, Mapping) and error.get("code") in {"resource_not_found", "not_found"}:
            raise PDIResourceNotFound("resource_not_found")
        raise PDIContractError("pdi_invalid_response")
    resource = payload.get("resource", payload)
    result = project_resource(resource, detail=True)
    assert isinstance(result, ResourceDetail)
    return result


def project_providers(aggregate_raw: Any, status_raw: Any, *, configured: Mapping[str, bool] | None = None) -> tuple[ProviderSummary, ...]:
    aggregate = _mapping(aggregate_raw)
    status = _mapping(status_raw)
    if aggregate.get("ok") is not True or status.get("ok") is not True:
        raise PDIContractError("pdi_invalid_response")
    buckets = aggregate.get("buckets")
    pipelines = status.get("pipelines")
    if not isinstance(buckets, list) or not isinstance(pipelines, list):
        raise PDIContractError("pdi_invalid_response")
    counts = {str(row.get("key", "")).lower(): int(row.get("count", 0)) for row in buckets if isinstance(row, Mapping) and isinstance(row.get("count"), int)}
    statuses = {row.get("pipeline_key"): row for row in pipelines if isinstance(row, Mapping) and isinstance(row.get("pipeline_key"), str)}
    configured = configured or {key: True for key in PROVIDERS}
    return tuple(_provider_summary(key, counts.get(key, 0), statuses, configured.get(key, False)) for key in ("gmail", "immich", "nextcloud"))


def provider_detail(summary: ProviderSummary) -> ProviderDetail:
    config = PROVIDERS.get(summary.provider_ref)
    if config is None:
        raise PDIProviderNotFound("provider_not_found")
    state = summary.operational_state
    stages = (("Source sync", "current" if state == "syncing" else "attention" if state == "attention" else "completed" if state in ("processing", "ready") else "pending"), ("Resource processing", "current" if state == "processing" else "attention" if state == "attention" else "completed" if state == "ready" else "pending"), ("Available to Jarvis", "completed" if state == "ready" else "pending"))
    return ProviderDetail(summary, str(config["description"]), tuple(config["capabilities"]), stages)


def _provider_summary(key: str, count: int, statuses: Mapping[str, Mapping[str, Any]], configured: bool) -> ProviderSummary:
    config = PROVIDERS[key]
    sync = statuses.get(config["sync"])
    dependencies = [statuses.get(name) for name in config["pipelines"]]
    rows = [row for row in [sync, *dependencies] if row is not None]
    if not configured or sync is None or sync.get("last_success_at") is None:
        state = "not_synced"
    elif sync.get("latest_status") == "running":
        state = "syncing"
    elif any(row.get("latest_status") == "running" for row in dependencies if row):
        state = "processing"
    elif any(row.get("latest_status") == "failed" or row.get("validated_after_dependencies") is False for row in rows):
        state = "attention"
    else:
        state = "ready"
    return ProviderSummary(key, key, str(config["name"]), str(config["category"]), configured, "read_only", max(0, count), state, _string(sync.get("last_success_at")) if sync and configured else None)


def _document_label(mime: str) -> str:
    if mime == "application/pdf": return "PDF"
    if "wordprocessing" in mime: return "DOCX"
    if "opendocument" in mime: return "ODT"
    if mime == "text/markdown": return "Markdown"
    return "Document"


def _format_size(value: int) -> str:
    if value < 1024: return f"{value} B"
    if value < 1024 ** 2: return f"{value / 1024:.1f} KiB"
    return f"{value / 1024 ** 2:.1f} MiB"
