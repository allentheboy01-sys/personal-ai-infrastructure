class ObservationError(Exception):
    """Stable base error for the Observation boundary."""

    code = "observation_error"


class ObservationValidationError(ObservationError, ValueError):
    code = "invalid_observation"


class ObservationResourceNotFoundError(ObservationError):
    code = "resource_not_found"


class ObservationExtractionError(ObservationError):
    code = "extraction_failed"


class ObservationLifecycleError(ObservationError):
    code = "ambiguous_document_generator_state"
