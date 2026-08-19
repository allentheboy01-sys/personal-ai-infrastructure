from datetime import UTC, datetime
from email.message import EmailMessage
import hashlib

import pytest

from pdi.observation import (
    EnrichmentResource,
    EnrichmentSource,
    GmailMetadataExtractor,
    GMAIL_FROM,
    GMAIL_INTERNAL_DATE,
    GMAIL_SUBJECT,
    GMAIL_TO,
)
from pdi.observation.errors import ObservationExtractionError


class _Reader:
    def __init__(self, raw):
        self.raw = raw

    def open(self, source):
        yield self.raw


def _raw():
    message = EmailMessage()
    message["Subject"] = "Synthetic subject"
    message["From"] = "Sender <sender@example.invalid>"
    message["To"] = "Receiver <receiver@example.invalid>"
    message.set_content("Synthetic body")
    message.add_attachment(b"synthetic", maintype="application", subtype="octet-stream", filename="fixture.bin")
    return message.as_bytes()


def _resource(raw):
    return EnrichmentResource(
        "pdi:resource:00000000-0000-0000-0000-000000000001",
        (EnrichmentSource(
            "source-1", "gmail", {"internalDate": "1722470400000"},
            provider_locator="synthetic-id",
            blob_sha256=hashlib.sha256(raw).hexdigest(),
            mime_type="message/rfc822",
        ),),
    )


def test_extracts_only_four_typed_facts_from_raw_and_bounded_metadata():
    raw = _raw()
    batch = GmailMetadataExtractor(_Reader(raw)).extract(_resource(raw))
    values = {draft.predicate: draft.value.value for draft in batch.statements}
    assert values[GMAIL_SUBJECT] == "Synthetic subject"
    assert values[GMAIL_FROM] == "Sender <sender@example.invalid>"
    assert values[GMAIL_TO] == "Receiver <receiver@example.invalid>"
    assert values[GMAIL_INTERNAL_DATE] == datetime(2024, 8, 1, tzinfo=UTC)
    assert set(values) == {GMAIL_SUBJECT, GMAIL_FROM, GMAIL_TO, GMAIL_INTERNAL_DATE}
    assert len(batch.statements) == 4


def test_fingerprint_changes_with_blob_or_internal_date():
    raw = _raw()
    extractor = GmailMetadataExtractor(_Reader(raw))
    first = _resource(raw)
    changed = EnrichmentResource(
        first.resource_ref,
        (EnrichmentSource(
            "source-1", "gmail", {"internalDate": "1722470401000"},
            provider_locator="synthetic-id",
            blob_sha256=hashlib.sha256(raw).hexdigest(),
        ),),
    )
    assert extractor.input_fingerprint(first) == extractor.input_fingerprint(first)
    assert extractor.input_fingerprint(first) != extractor.input_fingerprint(changed)


def test_content_hash_mismatch_fails_without_exposing_content():
    raw = _raw()
    resource = _resource(raw)
    with pytest.raises(ObservationExtractionError, match="no longer matches") as caught:
        GmailMetadataExtractor(_Reader(b"private body")).extract(resource)
    assert "private body" not in str(caught.value)
