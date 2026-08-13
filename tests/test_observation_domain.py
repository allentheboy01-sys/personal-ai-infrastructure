from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
import math
from types import MappingProxyType
from uuid import uuid4

import pytest

from pdi.observation import (
    EnrichmentSource,
    Evidence,
    EvidenceSourceKind,
    GeneratorIdentity,
    ObservationBatch,
    ObservationValidationError,
    PREDICATES,
    StatementDraft,
    StatementValueType,
    TypedStatementValue,
    get_predicate,
)
from pdi.query import format_resource_ref


RESOURCE_REF = format_resource_ref(uuid4())
FINGERPRINT = "a" * 64


def _draft(
    predicate: str = "media.camera_make",
    value_type: StatementValueType = StatementValueType.STRING,
    value: object = "Apple",
    confidence: float | None = None,
) -> StatementDraft:
    return StatementDraft(
        predicate=predicate,
        value=TypedStatementValue(value_type, value),
        evidence=Evidence(
            EvidenceSourceKind.PROVIDER_METADATA,
            f"asset_source.metadata.exif.{predicate}",
        ),
        confidence=confidence,
    )


def test_predicate_registry_is_frozen_and_unknown_rejected() -> None:
    assert isinstance(PREDICATES, MappingProxyType)
    assert get_predicate("media.captured_at").value_type == "datetime"
    with pytest.raises(ObservationValidationError):
        get_predicate("media.future_guess")
    with pytest.raises(TypeError):
        PREDICATES["new"] = get_predicate("media.captured_at")


@pytest.mark.parametrize(
    ("value_type", "value"),
    [
        (StatementValueType.STRING, 1),
        (StatementValueType.INTEGER, True),
        (StatementValueType.FLOAT, 1),
        (StatementValueType.BOOLEAN, 1),
        (StatementValueType.RESOURCE_REF, "pdi:resource:not-a-uuid"),
    ],
)
def test_typed_values_reject_mismatches(value_type, value) -> None:
    with pytest.raises((ObservationValidationError, ValueError)):
        TypedStatementValue(value_type, value)


def test_datetime_must_be_aware_and_is_normalized_to_utc() -> None:
    with pytest.raises(ObservationValidationError):
        TypedStatementValue(
            StatementValueType.DATETIME,
            datetime(2026, 1, 1),
        )
    value = TypedStatementValue(
        StatementValueType.DATETIME,
        datetime(2026, 1, 1, 8, tzinfo=UTC) + timedelta(hours=1),
    )
    assert value.value.tzinfo is UTC


@pytest.mark.parametrize("confidence", [0.0, 1.0, None])
def test_confidence_accepts_boundaries_and_null(confidence) -> None:
    assert _draft(confidence=confidence).confidence == confidence


@pytest.mark.parametrize(
    "confidence",
    [-0.1, 1.1, math.nan, math.inf, -math.inf, True, 1],
)
def test_confidence_rejects_invalid_values(confidence) -> None:
    with pytest.raises(ObservationValidationError):
        _draft(confidence=confidence)


def test_batch_validates_coverage_type_and_supports_zero_result() -> None:
    generator = GeneratorIdentity("deterministic_extractor", "test", "1")
    empty = ObservationBatch(
        RESOURCE_REF,
        generator,
        ("media.latitude", "media.longitude"),
        FINGERPRINT,
        (),
    )
    assert empty.statements == ()
    with pytest.raises(ObservationValidationError):
        ObservationBatch(
            RESOURCE_REF,
            generator,
            ("media.latitude",),
            FINGERPRINT,
            (_draft(),),
        )
    with pytest.raises(ObservationValidationError):
        ObservationBatch(
            RESOURCE_REF,
            generator,
            ("unknown",),
            FINGERPRINT,
            (),
        )


def test_dtos_and_nested_metadata_are_runtime_immutable() -> None:
    source = EnrichmentSource(
        source_id=str(uuid4()),
        provider="immich",
        metadata={"exif": {"nested": [1, {"value": 2}]}},
    )
    assert source.metadata["exif"]["nested"] == (1, {"value": 2})
    with pytest.raises(TypeError):
        source.metadata["exif"]["nested"][1]["value"] = 3
    with pytest.raises(FrozenInstanceError):
        source.provider = "nextcloud"
