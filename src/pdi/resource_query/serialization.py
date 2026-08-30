import json

from .models import CompactResource, ResourceQueryResult


def serialize_compact_resource(
    resource: CompactResource,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "resource_ref": resource.resource_ref,
        "title": resource.title,
        "resource_type": resource.resource_type,
        "mime_type": resource.mime_type,
        "mime_category": resource.mime_category,
        "providers": list(resource.providers),
        "relevant_time": (
            None
            if resource.relevant_time is None
            else resource.relevant_time.isoformat()
        ),
        "time_basis": resource.time_basis,
        "rank": resource.rank,
        "match_basis": resource.match_basis,
    }
    if resource.relative_path is not None:
        payload["relative_path"] = resource.relative_path
    return payload


def serialize_resource_query_result(
    result: ResourceQueryResult,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": result.schema,
        "query_kind": result.query_kind,
        "snapshot": result.snapshot.isoformat(),
        "selection_status": result.selection_status,
        "scanned_count": result.scanned_count,
        "resources": [
            serialize_compact_resource(resource)
            for resource in result.resources
        ],
        "continuation": result.continuation,
    }
    if result.bound_reason is not None:
        payload["bound_reason"] = result.bound_reason
    return payload


def serialized_result_bytes(result: ResourceQueryResult) -> int:
    return len(
        json.dumps(
            {"ok": True, **serialize_resource_query_result(result)},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
