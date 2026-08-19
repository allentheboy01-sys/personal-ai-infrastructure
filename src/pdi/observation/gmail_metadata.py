from collections.abc import Iterable
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
import hashlib
import json
import re

import requests

from pdi.adapters.base import ProviderFact
from pdi.adapters.gmail import GmailAdapter, GmailAdapterError

from .errors import ObservationExtractionError
from .models import (
    EnrichmentResource,
    EnrichmentSource,
    Evidence,
    EvidenceSourceKind,
    GeneratorIdentity,
    ObservationBatch,
    StatementDraft,
    StatementValueType,
    TypedStatementValue,
)
from .predicates import (
    GMAIL_FROM,
    GMAIL_INTERNAL_DATE,
    GMAIL_SUBJECT,
    GMAIL_TO,
)


MAX_RAW_MESSAGE_BYTES = 32 * 1024 * 1024
_SHA256_HEX = re.compile(r"[0-9a-fA-F]{64}")


def _error(code: str, message: str) -> ObservationExtractionError:
    error = ObservationExtractionError(message)
    error.code = code
    return error


def _selected_source(resource: EnrichmentResource) -> EnrichmentSource:
    sources = tuple(
        source
        for source in resource.sources
        if source.provider == "gmail" and source.is_active
    )
    if not sources:
        raise _error("no_active_gmail_source", "No active Gmail source")
    if len(sources) > 1:
        raise _error(
            "ambiguous_active_gmail_sources",
            "Multiple active Gmail sources are ambiguous",
        )
    source = sources[0]
    if (
        not isinstance(source.blob_sha256, str)
        or _SHA256_HEX.fullmatch(source.blob_sha256) is None
    ):
        raise _error(
            "invalid_blob_digest",
            "Gmail source has no valid current Blob digest",
        )
    return source


def _internal_date(source: EnrichmentSource) -> datetime | None:
    value = source.metadata.get("internalDate")
    if not isinstance(value, str) or not value.isdecimal():
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    except (ValueError, OverflowError, OSError):
        return None


def _fingerprint(source: EnrichmentSource) -> str:
    payload = {
        "format": "pdi.gmail_metadata.input.v1",
        "blob_sha256": source.blob_sha256.lower(),
        "internalDate": source.metadata.get("internalDate"),
        "extractor_version": "1",
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


class GmailRawReader:
    def __init__(self, adapter: GmailAdapter) -> None:
        self._adapter = adapter

    def open(self, source: EnrichmentSource) -> Iterable[bytes]:
        fact = ProviderFact(
            provider="gmail",
            kind="message",
            external_id=source.provider_locator,
            name=source.name,
            attributes={
                "path": None,
                "size": source.size,
                "mime_type": source.mime_type,
                "version_tag": source.version_tag,
                "content_hash": None,
            },
            raw={"internalDate": source.metadata.get("internalDate")},
        )
        try:
            yield from self._adapter.open(fact)
        except GmailAdapterError:
            raise _error(
                "provider_read_failed",
                "Gmail RAW content read failed",
            ) from None
        except (requests.RequestException, TypeError, ValueError):
            raise _error(
                "provider_invalid_source",
                "Gmail RAW content source is invalid",
            ) from None


def _read_raw(reader: GmailRawReader, source: EnrichmentSource) -> bytes:
    content = bytearray()
    stream = iter(reader.open(source))
    try:
        for chunk in stream:
            if not isinstance(chunk, bytes):
                raise _error(
                    "provider_invalid_response",
                    "Gmail RAW reader returned invalid bytes",
                )
            remaining = MAX_RAW_MESSAGE_BYTES + 1 - len(content)
            if remaining > 0:
                content.extend(chunk[:remaining])
            if len(content) > MAX_RAW_MESSAGE_BYTES:
                raise _error(
                    "source_too_large",
                    "Gmail RAW message exceeds the extraction limit",
                )
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()
    raw = bytes(content)
    if hashlib.sha256(raw).hexdigest() != source.blob_sha256.lower():
        raise _error(
            "content_changed_since_sync",
            "Gmail RAW content no longer matches the current Blob",
        )
    return raw


class GmailMetadataExtractor:
    generator = GeneratorIdentity(
        "deterministic_extractor",
        "gmail_metadata",
        "1",
    )
    covered_predicates = (
        GMAIL_SUBJECT,
        GMAIL_FROM,
        GMAIL_TO,
        GMAIL_INTERNAL_DATE,
    )

    def __init__(self, reader: GmailRawReader) -> None:
        self._reader = reader

    @staticmethod
    def is_eligible(resource: EnrichmentResource) -> bool:
        return any(
            source.provider == "gmail" and source.is_active
            for source in resource.sources
        )

    def input_fingerprint(self, resource: EnrichmentResource) -> str:
        return _fingerprint(_selected_source(resource))

    @staticmethod
    def _string_draft(predicate: str, value: str, locator: str):
        return StatementDraft(
            predicate,
            TypedStatementValue(StatementValueType.STRING, value),
            Evidence(EvidenceSourceKind.RESOURCE_CONTENT, locator),
            None,
        )

    def extract(self, resource: EnrichmentResource) -> ObservationBatch:
        source = _selected_source(resource)
        fingerprint = _fingerprint(source)
        message = BytesParser(policy=policy.default).parsebytes(
            _read_raw(self._reader, source)
        )
        drafts = []
        for predicate, header, locator in (
            (GMAIL_SUBJECT, "Subject", "gmail.raw.headers.subject"),
            (GMAIL_FROM, "From", "gmail.raw.headers.from"),
            (GMAIL_TO, "To", "gmail.raw.headers.to"),
        ):
            values = [str(value).strip() for value in message.get_all(header, [])]
            values = [value for value in values if value]
            if values:
                drafts.append(
                    self._string_draft(predicate, ", ".join(values), locator)
                )
        internal_date = _internal_date(source)
        if internal_date is not None:
            drafts.append(
                StatementDraft(
                    GMAIL_INTERNAL_DATE,
                    TypedStatementValue(
                        StatementValueType.DATETIME,
                        internal_date,
                    ),
                    Evidence(
                        EvidenceSourceKind.PROVIDER_METADATA,
                        "asset_source.metadata.internalDate",
                    ),
                    None,
                )
            )
        return ObservationBatch(
            resource.resource_ref,
            self.generator,
            self.covered_predicates,
            fingerprint,
            tuple(drafts),
        )
