from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from pdi.observation import (
    EnrichmentResource,
    EnrichmentSource,
    FileMetadataExtractor,
)
from pdi.query import format_resource_ref


NEXTCLOUD_TIME = "Sun, 10 Aug 2026 00:00:00 GMT"
IMMICH_TIME = "2026-08-10T00:00:00.000Z"


def _source(
    provider: str,
    value: object = None,
    *,
    source_id: str | None = None,
    active: bool = True,
    extra: dict | None = None,
) -> EnrichmentSource:
    key = (
        "getlastmodified"
        if provider == "nextcloud"
        else "fileModifiedAt"
    )
    metadata = {key: value, **(extra or {})}
    return EnrichmentSource(
        source_id or str(uuid4()),
        provider,
        metadata,
        is_active=active,
    )


def _resource(*sources: EnrichmentSource) -> EnrichmentResource:
    return EnrichmentResource(
        format_resource_ref(uuid4()),
        sources,
    )


def _value(resource: EnrichmentResource) -> datetime | None:
    statements = FileMetadataExtractor().extract(resource).statements
    return None if not statements else statements[0].value.value


def test_nextcloud_http_date_publishes_second_precision_utc() -> None:
    resource = _resource(_source("nextcloud", NEXTCLOUD_TIME))
    batch = FileMetadataExtractor().extract(resource)

    assert _value(resource) == datetime(2026, 8, 10, tzinfo=UTC)
    assert batch.statements[0].predicate == "file.modified_at"
    assert batch.statements[0].confidence is None
    assert batch.statements[0].evidence.source_kind == "provider_metadata"
    assert batch.statements[0].evidence.source_locator == (
        "nextcloud.webdav.getlastmodified"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "2026-08-10T08:00:00.123+08:00",
            datetime(2026, 8, 10, 0, 0, 0, 123000, tzinfo=UTC),
        ),
        (
            "2026-08-09T16:00:00.456-08:00",
            datetime(2026, 8, 10, 0, 0, 0, 456000, tzinfo=UTC),
        ),
        (
            "2026-08-10T00:00:00.789Z",
            datetime(2026, 8, 10, 0, 0, 0, 789000, tzinfo=UTC),
        ),
    ],
)
def test_immich_offsets_normalize_and_preserve_precision(
    raw: str,
    expected: datetime,
) -> None:
    assert _value(_resource(_source("immich", raw))) == expected


@pytest.mark.parametrize(
    "provider,raw",
    [
        ("nextcloud", None),
        ("nextcloud", ""),
        ("nextcloud", "not-an-http-date"),
        ("nextcloud", "2026-08-10"),
        ("immich", None),
        ("immich", ""),
        ("immich", "not-a-date"),
        ("immich", "2026-08-10"),
        ("immich", "2026-08-10T00:00:00"),
    ],
)
def test_missing_invalid_naive_and_date_only_are_unknown(
    provider: str,
    raw: object,
) -> None:
    assert _value(_resource(_source(provider, raw))) is None


def test_future_provider_timestamp_is_preserved() -> None:
    future = datetime.now(UTC) + timedelta(days=3650)
    raw = future.isoformat().replace("+00:00", "Z")
    assert _value(_resource(_source("immich", raw))) == future


def test_resource_level_consensus_across_supported_sources() -> None:
    extractor = FileMetadataExtractor()

    agreeing_nextcloud = _resource(
        _source("nextcloud", NEXTCLOUD_TIME),
        _source("nextcloud", NEXTCLOUD_TIME),
    )
    agreeing_cross_provider = _resource(
        _source("nextcloud", NEXTCLOUD_TIME),
        _source("immich", IMMICH_TIME),
    )
    disagreeing = _resource(
        _source("nextcloud", NEXTCLOUD_TIME),
        _source("immich", "2026-08-11T00:00:00Z"),
    )
    incomplete = _resource(
        _source("nextcloud", NEXTCLOUD_TIME),
        _source("immich", None),
    )

    assert len(extractor.extract(agreeing_nextcloud).statements) == 1
    cross_batch = extractor.extract(agreeing_cross_provider)
    assert len(cross_batch.statements) == 1
    assert cross_batch.statements[0].evidence.source_locator == (
        "file_metadata.active_supported_sources_consensus"
    )
    assert extractor.extract(disagreeing).statements == ()
    assert extractor.extract(incomplete).statements == ()


def test_unsupported_and_inactive_sources_do_not_block_consensus() -> None:
    valid = _source("nextcloud", NEXTCLOUD_TIME)
    unsupported = _source(
        "integration-test",
        "2020-01-01T00:00:00Z",
    )
    inactive = _source(
        "immich",
        "2026-08-11T00:00:00Z",
        active=False,
    )
    resource = _resource(valid, unsupported, inactive)

    assert FileMetadataExtractor().is_eligible(resource) is True
    assert _value(resource) == datetime(2026, 8, 10, tzinfo=UTC)


def test_no_supported_active_source_is_not_eligible() -> None:
    resource = _resource(
        _source("integration-test", "2026-08-10T00:00:00Z"),
        _source("immich", IMMICH_TIME, active=False),
    )
    extractor = FileMetadataExtractor()

    assert extractor.is_eligible(resource) is False
    assert extractor.extract(resource).statements == ()


def test_fingerprint_is_canonical_relevant_only_and_private() -> None:
    extractor = FileMetadataExtractor()
    resource_ref = format_resource_ref(uuid4())
    first_id = str(uuid4())
    second_id = str(uuid4())
    first = EnrichmentResource(
        resource_ref,
        (
            _source(
                "nextcloud",
                NEXTCLOUD_TIME,
                source_id=first_id,
                extra={"favorite": False},
            ),
            _source(
                "immich",
                IMMICH_TIME,
                source_id=second_id,
                extra={"exif": {"make": "A"}},
            ),
        ),
    )
    reordered_and_irrelevant_changed = EnrichmentResource(
        resource_ref,
        (
            _source(
                "immich",
                IMMICH_TIME,
                source_id=second_id,
                extra={"exif": {"make": "B"}},
            ),
            _source(
                "nextcloud",
                NEXTCLOUD_TIME,
                source_id=first_id,
                extra={"favorite": True},
            ),
        ),
    )
    changed = EnrichmentResource(
        resource_ref,
        (
            _source(
                "nextcloud",
                "Mon, 11 Aug 2026 00:00:00 GMT",
                source_id=first_id,
            ),
            _source(
                "immich",
                IMMICH_TIME,
                source_id=second_id,
            ),
        ),
    )

    first_fingerprint = extractor.input_fingerprint(first)
    assert first_fingerprint == extractor.input_fingerprint(
        reordered_and_irrelevant_changed
    )
    assert first_fingerprint != extractor.input_fingerprint(changed)
    assert first_id not in first_fingerprint
    assert second_id not in first_fingerprint
    assert len(first_fingerprint) == 64
