from types import MappingProxyType

from .models import (
    PredicateCardinality,
    PredicateDefinition,
    StatementValueType,
)


MEDIA_CAPTURED_AT = "media.captured_at"
MEDIA_LATITUDE = "media.latitude"
MEDIA_LONGITUDE = "media.longitude"
MEDIA_CAMERA_MAKE = "media.camera_make"
MEDIA_CAMERA_MODEL = "media.camera_model"
MEDIA_OCR_TEXT = "media.ocr_text"
DOCUMENT_TEXT_EXCERPT = "document.text_excerpt"
FILE_MODIFIED_AT = "file.modified_at"


PREDICATES = MappingProxyType(
    {
        MEDIA_CAPTURED_AT: PredicateDefinition(
            name=MEDIA_CAPTURED_AT,
            value_type=StatementValueType.DATETIME,
            cardinality=PredicateCardinality.SINGLE,
        ),
        MEDIA_LATITUDE: PredicateDefinition(
            name=MEDIA_LATITUDE,
            value_type=StatementValueType.FLOAT,
            cardinality=PredicateCardinality.SINGLE,
        ),
        MEDIA_LONGITUDE: PredicateDefinition(
            name=MEDIA_LONGITUDE,
            value_type=StatementValueType.FLOAT,
            cardinality=PredicateCardinality.SINGLE,
        ),
        MEDIA_CAMERA_MAKE: PredicateDefinition(
            name=MEDIA_CAMERA_MAKE,
            value_type=StatementValueType.STRING,
            cardinality=PredicateCardinality.SINGLE,
        ),
        MEDIA_CAMERA_MODEL: PredicateDefinition(
            name=MEDIA_CAMERA_MODEL,
            value_type=StatementValueType.STRING,
            cardinality=PredicateCardinality.SINGLE,
        ),
        MEDIA_OCR_TEXT: PredicateDefinition(
            name=MEDIA_OCR_TEXT,
            value_type=StatementValueType.STRING,
            cardinality=PredicateCardinality.SINGLE,
        ),
        DOCUMENT_TEXT_EXCERPT: PredicateDefinition(
            name=DOCUMENT_TEXT_EXCERPT,
            value_type=StatementValueType.STRING,
            cardinality=PredicateCardinality.SINGLE,
        ),
        FILE_MODIFIED_AT: PredicateDefinition(
            name=FILE_MODIFIED_AT,
            value_type=StatementValueType.DATETIME,
            cardinality=PredicateCardinality.SINGLE,
        ),
    }
)


def get_predicate(name: str) -> PredicateDefinition:
    from .errors import ObservationValidationError

    try:
        return PREDICATES[name]
    except (KeyError, TypeError) as error:
        raise ObservationValidationError(
            f"Unknown observation predicate: {name!r}"
        ) from error
