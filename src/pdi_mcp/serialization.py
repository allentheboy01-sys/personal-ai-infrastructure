from pdi.query import (
    ContentSummary,
    ResourceAggregationResult,
    ResourceDetail,
    ResourceFilters,
    ResourceSourceSummary,
    ResourceSummary,
)
from pdi.observation import StatementValueType, StatementView


def _serialize_filters(filters: ResourceFilters) -> dict[str, object]:
    return {
        "provider": filters.provider,
        "resource_type": filters.resource_type,
        "mime_type": filters.mime_type,
        "mime_category": filters.mime_category,
        "path_prefix": filters.path_prefix,
    }


def serialize_source(source: ResourceSourceSummary) -> dict[str, object]:
    return {
        "provider": source.provider,
        "location": source.location,
        "name": source.name,
        "mime_type": source.mime_type,
        "size_bytes": source.size_bytes,
        "is_active": source.is_active,
    }


def serialize_resource_summary(
    resource: ResourceSummary,
) -> dict[str, object]:
    return {
        "resource_ref": resource.resource_ref,
        "resource_type": resource.resource_type,
        "display_name": resource.display_name,
        "pdi_first_observed_at": (
            resource.pdi_first_observed_at.isoformat()
        ),
        "sources": [
            serialize_source(source)
            for source in resource.sources
        ],
    }


def serialize_content(content: ContentSummary) -> dict[str, object]:
    return {
        "mime_type": content.mime_type,
        "size_bytes": content.size_bytes,
        "checksum": content.checksum,
    }


def serialize_resource_detail(
    resource: ResourceDetail,
) -> dict[str, object]:
    return {
        "resource_ref": resource.resource_ref,
        "resource_type": resource.resource_type,
        "display_name": resource.display_name,
        "pdi_first_observed_at": (
            resource.pdi_first_observed_at.isoformat()
        ),
        "sources": [
            serialize_source(source)
            for source in resource.sources
        ],
        "content_variants": [
            serialize_content(content)
            for content in resource.content_variants
        ],
    }


def serialize_resource_aggregation(
    result: ResourceAggregationResult,
) -> dict[str, object]:
    return {
        "time_basis": result.time_basis,
        "observed_from": (
            None
            if result.time_range.observed_from is None
            else result.time_range.observed_from.isoformat()
        ),
        "observed_to": (
            None
            if result.time_range.observed_to is None
            else result.time_range.observed_to.isoformat()
        ),
        "applied_filters": _serialize_filters(
            result.applied_filters
        ),
        "group_by": (
            None if result.group_by is None else result.group_by.value
        ),
        "total_count": result.total_count,
        "buckets": [
            {
                "key": bucket.key,
                "count": bucket.count,
            }
            for bucket in result.buckets
        ],
        "buckets_truncated": result.buckets_truncated,
    }


def serialize_statement(statement: StatementView) -> dict[str, object]:
    value: object = statement.value
    if statement.value_type is StatementValueType.DATETIME:
        value = statement.value.isoformat()
    return {
        "subject_resource_ref": statement.subject_resource_ref,
        "predicate": statement.predicate,
        "value_type": statement.value_type.value,
        "value": value,
        "generator_type": statement.generator.generator_type,
        "generator_name": statement.generator.generator_name,
        "generator_version": statement.generator.generator_version,
        "source_kind": statement.evidence.source_kind.value,
        "source_locator": statement.evidence.source_locator,
        "confidence": statement.confidence,
        "created_at": statement.created_at.isoformat(),
    }
