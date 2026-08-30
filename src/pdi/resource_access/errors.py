class ResourceAccessError(Exception):
    """Stable base error for Resource representation access."""

    code = "resource_access_error"


class InvalidResourceReferenceError(ResourceAccessError):
    code = "invalid_resource_ref"


class UnsupportedRepresentationError(ResourceAccessError):
    code = "unsupported_representation"


class ResourceNotFoundError(ResourceAccessError):
    code = "resource_not_found"


class RepresentationUnavailableError(ResourceAccessError):
    code = "representation_unavailable"


class AmbiguousAccessSourceError(ResourceAccessError):
    code = "ambiguous_access_source"


class ProviderUnavailableError(ResourceAccessError):
    code = "provider_unavailable"


class ProviderInvalidResponseError(ResourceAccessError):
    code = "provider_invalid_response"


class RepresentationTooLargeError(ResourceAccessError):
    code = "representation_too_large"


class ResourceAccessUnavailableError(ResourceAccessError):
    """Persistence/configuration failure safe for external serialization."""

    code = "resource_access_unavailable"


class TextUnavailableError(ResourceAccessError):
    code = "text_unavailable"


class AmbiguousTextContentError(ResourceAccessError):
    code = "ambiguous_text_content"


class TextTooLargeError(ResourceAccessError):
    code = "text_too_large"


class InvalidTextWindowError(ResourceAccessError, ValueError):
    code = "invalid_text_window"


class InvalidTextContentError(ResourceAccessError):
    code = "invalid_text_content"


class ContentChangedSinceSyncError(ResourceAccessError):
    code = "content_changed_since_sync"
