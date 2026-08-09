from pdi.query import (
    ContentSummary,
    ResourceDetail,
    ResourceSourceSummary,
    ResourceSummary,
)


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
