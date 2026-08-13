from datetime import UTC, datetime
import math
from uuid import uuid4

import pytest

from pdi.observation import (
    EnrichmentResource,
    EnrichmentSource,
    ImmichMetadataExtractor,
    ObservationExtractionError,
)
from pdi.query import format_resource_ref


def _resource(exif: dict, *, extra: dict | None = None) -> EnrichmentResource:
    metadata = {"exif": exif, **(extra or {})}
    return EnrichmentResource(
        format_resource_ref(uuid4()),
        (EnrichmentSource(str(uuid4()), "immich", metadata),),
    )


def test_extracts_typed_persisted_metadata_without_http() -> None:
    extractor = ImmichMetadataExtractor()
    resource = _resource({
        "dateTimeOriginal": "2020-01-02T03:04:05+08:00",
        "latitude": 31.2,
        "longitude": 121.5,
        "make": "Apple",
        "model": "iPhone",
    })
    batch = extractor.extract(resource)
    values = {draft.predicate: draft.value.value for draft in batch.statements}
    assert values == {
        "media.captured_at": datetime(2020, 1, 1, 19, 4, 5, tzinfo=UTC),
        "media.latitude": 31.2,
        "media.longitude": 121.5,
        "media.camera_make": "Apple",
        "media.camera_model": "iPhone",
    }
    assert all(draft.confidence is None for draft in batch.statements)
    assert all(draft.evidence.source_kind == "provider_metadata" for draft in batch.statements)
    assert not hasattr(extractor, "connect") and not hasattr(extractor, "open")


@pytest.mark.parametrize("captured", [None, "", "not-a-date", "2020-01-01T00:00:00"])
def test_missing_invalid_or_naive_capture_time_is_not_published(captured) -> None:
    batch = ImmichMetadataExtractor().extract(_resource({"dateTimeOriginal": captured}))
    assert "media.captured_at" not in {draft.predicate for draft in batch.statements}


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (1.0, None),
        (None, 1.0),
        (91.0, 1.0),
        (1.0, 181.0),
        (math.nan, 1.0),
        (1.0, math.inf),
        (True, 1.0),
    ],
)
def test_gps_requires_one_valid_finite_pair(latitude, longitude) -> None:
    batch = ImmichMetadataExtractor().extract(
        _resource({"latitude": latitude, "longitude": longitude})
    )
    predicates = {draft.predicate for draft in batch.statements}
    assert "media.latitude" not in predicates
    assert "media.longitude" not in predicates


@pytest.mark.parametrize(
    ("make", "model", "expected"),
    [
        ("Apple", None, {"media.camera_make"}),
        (None, "iPhone", {"media.camera_model"}),
        ("", "   ", set()),
    ],
)
def test_camera_fields_are_independent_nonempty_strings(make, model, expected) -> None:
    batch = ImmichMetadataExtractor().extract(_resource({"make": make, "model": model}))
    assert {draft.predicate for draft in batch.statements} == expected


def test_fingerprint_is_canonical_relevant_only_and_sensitive() -> None:
    extractor = ImmichMetadataExtractor()
    source_id = str(uuid4())
    ref = format_resource_ref(uuid4())
    first = EnrichmentResource(ref, (EnrichmentSource(source_id, "immich", {"exif": {"make": "Apple", "model": "iPhone"}, "irrelevant": 1}),))
    reordered = EnrichmentResource(ref, (EnrichmentSource(source_id, "immich", {"irrelevant": 2, "exif": {"model": "iPhone", "make": "Apple"}}),))
    changed = EnrichmentResource(ref, (EnrichmentSource(source_id, "immich", {"exif": {"make": "Canon", "model": "iPhone"}}),))
    assert extractor.input_fingerprint(first) == extractor.input_fingerprint(reordered)
    assert extractor.input_fingerprint(first) != extractor.input_fingerprint(changed)


def test_zero_and_multiple_active_immich_sources_are_not_arbitrarily_selected() -> None:
    extractor = ImmichMetadataExtractor()
    ref = format_resource_ref(uuid4())
    with pytest.raises(ObservationExtractionError):
        extractor.extract(EnrichmentResource(ref, ()))
    multiple = EnrichmentResource(ref, (
        EnrichmentSource(str(uuid4()), "immich", {"exif": {}}),
        EnrichmentSource(str(uuid4()), "immich", {"exif": {}}),
    ))
    assert len(extractor.input_fingerprint(multiple)) == 64
    with pytest.raises(ObservationExtractionError) as caught:
        extractor.extract(multiple)
    assert caught.value.code == "ambiguous_active_immich_sources"
