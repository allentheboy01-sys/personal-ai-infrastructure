class RichRetrievalError(Exception):
    """Stable base error for bounded Rich Retrieval composition."""

    code = "rich_retrieval_error"


class InvalidRichRetrievalStateError(RichRetrievalError):
    """The persisted observations cannot be interpreted unambiguously."""

    code = "invalid_observation_state"
