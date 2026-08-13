from datetime import datetime
import hashlib
import json
import math

from .errors import ObservationExtractionError
from .models import (
    EnrichmentResource,
    Evidence,
    EvidenceSourceKind,
    GeneratorIdentity,
    ObservationBatch,
    StatementDraft,
    StatementValueType,
    TypedStatementValue,
)
from .predicates import (
    MEDIA_CAMERA_MAKE,
    MEDIA_CAMERA_MODEL,
    MEDIA_CAPTURED_AT,
    MEDIA_LATITUDE,
    MEDIA_LONGITUDE,
)


class ImmichMetadataExtractor:
    generator = GeneratorIdentity("deterministic_extractor", "immich_metadata", "1")
    covered_predicates = (
        MEDIA_CAPTURED_AT, MEDIA_LATITUDE, MEDIA_LONGITUDE,
        MEDIA_CAMERA_MAKE, MEDIA_CAMERA_MODEL,
    )

    @staticmethod
    def _selected_source(resource: EnrichmentResource):
        sources = tuple(source for source in resource.sources if source.provider == "immich")
        if not sources:
            raise ObservationExtractionError("No active Immich source")
        if len(sources) > 1:
            error = ObservationExtractionError("Multiple active Immich sources are ambiguous")
            error.code = "ambiguous_active_immich_sources"
            raise error
        return sources[0]

    @staticmethod
    def _relevant(source) -> dict[str, object]:
        exif = source.metadata.get("exif")
        if not isinstance(exif, dict) and not hasattr(exif, "get"):
            exif = {}
        return {key: exif.get(key) for key in ("dateTimeOriginal", "latitude", "longitude", "make", "model")}

    def input_fingerprint(self, resource: EnrichmentResource) -> str:
        sources = tuple(
            source for source in resource.sources
            if source.provider == "immich"
        )
        if not sources:
            raise ObservationExtractionError("No active Immich source")
        if len(sources) == 1:
            source = sources[0]
            payload = {
                "source_id": source.source_id,
                "exif": self._relevant(source),
            }
        else:
            payload = {
                "ambiguous_source_ids": sorted(
                    source.source_id for source in sources
                )
            }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _draft(predicate, value_type, value, locator):
        return StatementDraft(
            predicate, TypedStatementValue(value_type, value),
            Evidence(EvidenceSourceKind.PROVIDER_METADATA, locator), None,
        )

    def extract(self, resource: EnrichmentResource) -> ObservationBatch:
        source = self._selected_source(resource)
        values = self._relevant(source)
        drafts = []
        captured = values["dateTimeOriginal"]
        if isinstance(captured, str):
            try:
                parsed = datetime.fromisoformat(captured.replace("Z", "+00:00"))
                if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                    drafts.append(self._draft(MEDIA_CAPTURED_AT, StatementValueType.DATETIME, parsed, "asset_source.metadata.exif.dateTimeOriginal"))
            except ValueError:
                pass
        lat, lon = values["latitude"], values["longitude"]
        valid_lat = type(lat) in (int, float) and math.isfinite(lat) and -90 <= lat <= 90
        valid_lon = type(lon) in (int, float) and math.isfinite(lon) and -180 <= lon <= 180
        if valid_lat and valid_lon:
            drafts.extend((
                self._draft(MEDIA_LATITUDE, StatementValueType.FLOAT, float(lat), "asset_source.metadata.exif.latitude"),
                self._draft(MEDIA_LONGITUDE, StatementValueType.FLOAT, float(lon), "asset_source.metadata.exif.longitude"),
            ))
        for predicate, key in ((MEDIA_CAMERA_MAKE, "make"), (MEDIA_CAMERA_MODEL, "model")):
            value = values[key]
            if isinstance(value, str) and value.strip():
                drafts.append(self._draft(predicate, StatementValueType.STRING, value, f"asset_source.metadata.exif.{key}"))
        return ObservationBatch(resource.resource_ref, self.generator, self.covered_predicates, self.input_fingerprint(resource), tuple(drafts))
