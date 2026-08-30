from pdi.query import QueryError


class ResourceQueryError(QueryError):
    """Stable base error for the unified public Resource query."""

    code = "resource_query_error"


class InvalidResourceQueryPrimaryError(ResourceQueryError, ValueError):
    code = "invalid_resource_query_primary"


class InvalidResourceQueryFiltersError(ResourceQueryError, ValueError):
    code = "invalid_resource_query_filters"


class InvalidResourceQuerySortError(ResourceQueryError, ValueError):
    code = "invalid_resource_query_sort"


class InvalidResourceQueryContinuationError(
    ResourceQueryError,
    ValueError,
):
    code = "invalid_resource_query_continuation"


class ResourceQueryProjectionError(ResourceQueryError):
    code = "resource_query_projection_error"


class ResourceQueryUnavailableError(ResourceQueryError):
    code = "resource_query_unavailable"
