from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import hashlib
import json
from typing import NamedTuple

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
from .predicates import FILE_MODIFIED_AT


class _TemporalInput(NamedTuple):
    source: EnrichmentSource
    raw_value: object
    parse_state: str
    normalized: datetime | None


class FileMetadataExtractor:
    """Derive one Resource-level file modification consensus."""

    generator = GeneratorIdentity(
        "deterministic_extractor",
        "file_metadata",
        "1",
    )
    covered_predicates = (FILE_MODIFIED_AT,)
    discovery_providers = ("nextcloud", "immich")

    @classmethod
    def _eligible_sources(
        cls,
        resource: EnrichmentResource,
    ) -> tuple[EnrichmentSource, ...]:
        return tuple(
            source
            for source in resource.sources
            if source.is_active
            and source.provider in cls.discovery_providers
        )

    @classmethod
    def is_eligible(cls, resource: EnrichmentResource) -> bool:
        return bool(cls._eligible_sources(resource))

    @staticmethod
    def _raw_value(source: EnrichmentSource) -> object:
        if source.provider == "nextcloud":
            return source.metadata.get("getlastmodified")
        return source.metadata.get("fileModifiedAt")

    @staticmethod
    def _parse_nextcloud(value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(UTC)

    @staticmethod
    def _parse_immich(value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(UTC)

    @classmethod
    def _temporal_input(
        cls,
        source: EnrichmentSource,
    ) -> _TemporalInput:
        raw_value = cls._raw_value(source)
        if raw_value is None or raw_value == "":
            return _TemporalInput(source, raw_value, "missing", None)
        if source.provider == "nextcloud":
            normalized = cls._parse_nextcloud(raw_value)
        else:
            normalized = cls._parse_immich(raw_value)
        return _TemporalInput(
            source,
            raw_value,
            "valid" if normalized is not None else "invalid",
            normalized,
        )

    @classmethod
    def _inputs(
        cls,
        resource: EnrichmentResource,
    ) -> tuple[_TemporalInput, ...]:
        return tuple(
            cls._temporal_input(source)
            for source in cls._eligible_sources(resource)
        )

    def input_fingerprint(self, resource: EnrichmentResource) -> str:
        inputs = self._inputs(resource)
        payload = {
            "generator": {
                "type": self.generator.generator_type,
                "name": self.generator.generator_name,
                "version": self.generator.generator_version,
            },
            "sources": sorted(
                (
                    {
                        "provider": item.source.provider,
                        "source_id": item.source.source_id,
                        "raw_value": item.raw_value,
                        "parse_state": item.parse_state,
                        "normalized": (
                            None
                            if item.normalized is None
                            else item.normalized.isoformat()
                        ),
                    }
                    for item in inputs
                ),
                key=lambda item: (
                    str(item["provider"]),
                    str(item["source_id"]),
                ),
            ),
        }
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode()
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _evidence_locator(inputs: tuple[_TemporalInput, ...]) -> str:
        providers = {item.source.provider for item in inputs}
        if providers == {"nextcloud"}:
            return "nextcloud.webdav.getlastmodified"
        if providers == {"immich"}:
            return "immich.asset.fileModifiedAt"
        return "file_metadata.active_supported_sources_consensus"

    def extract(self, resource: EnrichmentResource) -> ObservationBatch:
        inputs = self._inputs(resource)
        values = {
            item.normalized
            for item in inputs
            if item.normalized is not None
        }
        complete_consensus = (
            bool(inputs)
            and all(item.parse_state == "valid" for item in inputs)
            and len(values) == 1
        )
        statements: tuple[StatementDraft, ...] = ()
        if complete_consensus:
            value = next(iter(values))
            statements = (
                StatementDraft(
                    predicate=FILE_MODIFIED_AT,
                    value=TypedStatementValue(
                        StatementValueType.DATETIME,
                        value,
                    ),
                    evidence=Evidence(
                        EvidenceSourceKind.PROVIDER_METADATA,
                        self._evidence_locator(inputs),
                    ),
                    confidence=None,
                ),
            )
        return ObservationBatch(
            resource.resource_ref,
            self.generator,
            self.covered_predicates,
            self.input_fingerprint(resource),
            statements,
        )
