import math
from uuid import uuid4

import pytest

from pdi.observation import (
    EnrichmentResource,
    EnrichmentSource,
    ImmichGeoExtractor,
    ObservationExtractionError,
    PREDICATES,
)
from pdi.query import format_resource_ref


def _source(
    exif: dict,
    *,
    provider: str = "immich",
    active: bool = True,
    source_id: str | None = None,
    extra: dict | None = None,
) -> EnrichmentSource:
    return EnrichmentSource(
        source_id or str(uuid4()),
        provider,
        {"exif": exif, **(extra or {})},
        is_active=active,
    )


def _resource(*sources: EnrichmentSource) -> EnrichmentResource:
    return EnrichmentResource(
        format_resource_ref(uuid4()),
        sources,
    )


def _values(resource: EnrichmentResource) -> dict[str, object]:
    batch = ImmichGeoExtractor().extract(resource)
    return {
        statement.predicate: statement.value.value
        for statement in batch.statements
    }


def test_registers_exact_frozen_geo_predicates() -> None:
    geo = {
        name: definition
        for name, definition in PREDICATES.items()
        if name.startswith("geo.")
    }

    assert set(geo) == {
        "geo.country",
        "geo.admin1",
        "geo.locality",
    }
    assert all(item.value_type == "string" for item in geo.values())
    assert all(item.cardinality == "single" for item in geo.values())


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (0, 0),
        (-90, -180),
        (90, 180),
        (31.2, 121.5),
    ],
)
def test_valid_coordinate_pair_projects_all_provider_labels(
    latitude,
    longitude,
) -> None:
    extractor = ImmichGeoExtractor()
    batch = extractor.extract(_resource(_source({
        "latitude": latitude,
        "longitude": longitude,
        "country": "People's Republic of China",
        "state": "Shanghai",
        "city": "Shanghai",
    })))

    assert extractor.generator.generator_type == "deterministic_extractor"
    assert extractor.generator.generator_name == "immich_geo"
    assert extractor.generator.generator_version == "1"
    assert batch.covered_predicates == (
        "geo.country",
        "geo.admin1",
        "geo.locality",
    )
    assert {
        statement.predicate: statement.value.value
        for statement in batch.statements
    } == {
        "geo.country": "People's Republic of China",
        "geo.admin1": "Shanghai",
        "geo.locality": "Shanghai",
    }
    assert all(
        statement.value.value_type == "string"
        and statement.evidence.source_kind == "provider_metadata"
        and statement.confidence is None
        for statement in batch.statements
    )
    assert {
        statement.evidence.source_locator
        for statement in batch.statements
    } == {
        "immich.asset.exifInfo.country",
        "immich.asset.exifInfo.state",
        "immich.asset.exifInfo.city",
    }


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (None, 1.0),
        (1.0, None),
        (math.nan, 1.0),
        (1.0, math.inf),
        (-91.0, 1.0),
        (91.0, 1.0),
        (1.0, -181.0),
        (1.0, 181.0),
        (True, 1.0),
        (1.0, False),
        ("31.2", 121.5),
        (31.2, "121.5"),
    ],
)
def test_missing_partial_or_invalid_coordinates_are_zero_result(
    latitude,
    longitude,
) -> None:
    resource = _resource(_source({
        "latitude": latitude,
        "longitude": longitude,
        "country": "United Kingdom",
        "state": "England",
        "city": "Cambridge",
    }))

    assert _values(resource) == {}


@pytest.mark.parametrize(
    ("country", "state", "city", "expected"),
    [
        (
            "United Kingdom",
            None,
            None,
            {"geo.country": "United Kingdom"},
        ),
        (
            "United Kingdom",
            "England",
            None,
            {
                "geo.country": "United Kingdom",
                "geo.admin1": "England",
            },
        ),
        (
            "People's Republic of China",
            "Guangdong",
            "深圳市",
            {
                "geo.country": "People's Republic of China",
                "geo.admin1": "Guangdong",
                "geo.locality": "深圳市",
            },
        ),
        ("", "   ", None, {}),
        ("  Provider Label  ", None, None, {
            "geo.country": "  Provider Label  ",
        }),
    ],
)
def test_partial_unicode_and_empty_label_semantics(
    country,
    state,
    city,
    expected,
) -> None:
    assert _values(_resource(_source({
        "latitude": 1.0,
        "longitude": 2.0,
        "country": country,
        "state": state,
        "city": city,
    }))) == expected


@pytest.mark.parametrize("field", ["country", "state", "city"])
def test_wrong_non_null_label_type_is_structural_failure(field) -> None:
    exif = {
        "latitude": 1.0,
        "longitude": 2.0,
        "country": "Country",
        "state": "Admin1",
        "city": "Locality",
    }
    exif[field] = 123

    with pytest.raises(ObservationExtractionError) as caught:
        _values(_resource(_source(exif)))
    assert caught.value.code == "invalid_immich_geo_metadata"


def test_source_selection_ignores_unsupported_and_inactive_sources() -> None:
    extractor = ImmichGeoExtractor()
    active = _source({
        "latitude": 1.0,
        "longitude": 2.0,
        "country": "Country",
    })
    resource = _resource(
        _source(
            {"latitude": 9.0, "longitude": 9.0, "country": "Wrong"},
            provider="nextcloud",
        ),
        _source(
            {"latitude": 8.0, "longitude": 8.0, "country": "Wrong"},
            active=False,
        ),
        active,
    )

    assert extractor.is_eligible(resource) is True
    assert _values(resource) == {"geo.country": "Country"}

    unsupported_only = _resource(
        _source({}, provider="nextcloud"),
        _source({}, active=False),
    )
    assert extractor.is_eligible(unsupported_only) is False
    with pytest.raises(ObservationExtractionError) as caught:
        extractor.extract(unsupported_only)
    assert caught.value.code == "no_active_immich_source"


def test_multiple_active_immich_sources_fail_without_arbitration() -> None:
    extractor = ImmichGeoExtractor()
    resource = _resource(
        _source({"latitude": 1.0, "longitude": 2.0}),
        _source({"latitude": 1.0, "longitude": 2.0}),
    )

    assert extractor.is_eligible(resource) is True
    assert len(extractor.input_fingerprint(resource)) == 64
    with pytest.raises(ObservationExtractionError) as caught:
        extractor.extract(resource)
    assert caught.value.code == "ambiguous_active_immich_sources"


def test_fingerprint_is_private_relevant_only_and_sensitive() -> None:
    extractor = ImmichGeoExtractor()
    source_id = str(uuid4())
    ref = format_resource_ref(uuid4())

    def resource(exif, extra=None, identifier=source_id):
        return EnrichmentResource(
            ref,
            (_source(
                exif,
                source_id=identifier,
                extra=extra,
            ),),
        )

    first = resource({
        "latitude": 31.2,
        "longitude": 121.5,
        "country": "Country",
        "state": "Admin1",
        "city": "Locality",
        "make": "Camera A",
    }, {"favorite": False})
    unrelated_changed = resource({
        "city": "Locality",
        "state": "Admin1",
        "country": "Country",
        "longitude": 121.5,
        "latitude": 31.2,
        "make": "Camera B",
    }, {"favorite": True})
    label_changed = resource({
        "latitude": 31.2,
        "longitude": 121.5,
        "country": "Country",
        "state": "Admin1",
        "city": "Other Locality",
    })
    coordinate_changed = resource({
        "latitude": 31.200001,
        "longitude": 121.5,
        "country": "Country",
        "state": "Admin1",
        "city": "Locality",
    })
    source_changed = resource({
        "latitude": 31.2,
        "longitude": 121.5,
        "country": "Country",
        "state": "Admin1",
        "city": "Locality",
    }, identifier=str(uuid4()))

    fingerprint = extractor.input_fingerprint(first)
    assert fingerprint == extractor.input_fingerprint(unrelated_changed)
    assert fingerprint != extractor.input_fingerprint(label_changed)
    assert fingerprint != extractor.input_fingerprint(coordinate_changed)
    assert fingerprint != extractor.input_fingerprint(source_changed)
    assert source_id not in fingerprint
    assert len(fingerprint) == 64
    assert not hasattr(extractor, "connect")
    assert not hasattr(extractor, "open")
