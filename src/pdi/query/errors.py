class QueryError(Exception):
    """Stable base error for the read-only Query boundary."""

    code = "query_error"


class InvalidQueryError(QueryError, ValueError):
    code = "invalid_query"


class InvalidResourceRefError(QueryError, ValueError):
    code = "invalid_resource_ref"


class ResourceNotFoundError(QueryError):
    code = "resource_not_found"
