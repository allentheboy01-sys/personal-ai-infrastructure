class RetrievalError(Exception):
    """Stable base error for provider-native retrieval."""

    code = "retrieval_error"


class ProviderUnavailableError(RetrievalError):
    code = "provider_unavailable"


class ProviderCapabilityUnavailableError(RetrievalError):
    code = "provider_capability_unavailable"


class ProviderInvalidResponseError(RetrievalError):
    code = "provider_invalid_response"


class RetrievalMappingError(RetrievalError):
    code = "mapping_error"
