from collections.abc import Mapping
import hashlib
import json
import math

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
from .predicates import GEO_ADMIN1, GEO_COUNTRY, GEO_LOCALITY


class ImmichGeoExtractor:
    """Project labels from Immich's local GeoNames/Natural Earth pipeline.

    Extraction reads only persisted Provider metadata and performs no
    reverse-geocoder or Provider network request.
    """

    generator = GeneratorIdentity(
        "deterministic_extractor",
        "immich_geo",
        "1",
    )
    covered_predicates = (
        GEO_COUNTRY,
        GEO_ADMIN1,
        GEO_LOCALITY,
    )

    _LABELS = (
        (GEO_COUNTRY, "country", "immich.asset.exifInfo.country"),
        (GEO_ADMIN1, "state", "immich.asset.exifInfo.state"),
        (GEO_LOCALITY, "city", "immich.asset.exifInfo.city"),
    )

    @staticmethod
    def _active_sources(
        resource: EnrichmentResource,
    ) -> tuple[EnrichmentSource, ...]:
        return tuple(
            source
            for source in resource.sources
            if source.provider == "immich" and source.is_active
        )

    @classmethod
    def is_eligible(cls, resource: EnrichmentResource) -> bool:
        return bool(cls._active_sources(resource))

    @classmethod
    def _selected_source(
        cls,
        resource: EnrichmentResource,
    ) -> EnrichmentSource:
        sources = cls._active_sources(resource)
        if not sources:
            error = ObservationExtractionError(
                "No active Immich source"
            )
            error.code = "no_active_immich_source"
            raise error
        if len(sources) > 1:
            error = ObservationExtractionError(
                "Multiple active Immich sources are ambiguous"
            )
            error.code = "ambiguous_active_immich_sources"
            raise error
        return sources[0]

    @staticmethod
    def _relevant(source: EnrichmentSource) -> dict[str, object]:
        exif = source.metadata.get("exif")
        if not isinstance(exif, Mapping):
            exif = {}
        return {
            key: exif.get(key)
            for key in (
                "latitude",
                "longitude",
                "country",
                "state",
                "city",
            )
        }

    def input_fingerprint(self, resource: EnrichmentResource) -> str:
        sources = self._active_sources(resource)
        generator = {
            "type": self.generator.generator_type,
            "name": self.generator.generator_name,
            "version": self.generator.generator_version,
        }
        if len(sources) == 1:
            payload = {
                "generator": generator,
                "source_id": sources[0].source_id,
                "geo": self._relevant(sources[0]),
            }
        else:
            payload = {
                "generator": generator,
                "ambiguous_source_ids": sorted(
                    source.source_id for source in sources
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
    def _valid_coordinates(latitude: object, longitude: object) -> bool:
        return (
            type(latitude) in (int, float)
            and type(longitude) in (int, float)
            and math.isfinite(latitude)
            and math.isfinite(longitude)
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
        )

    @staticmethod
    def _label(value: object, field: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            error = ObservationExtractionError(
                f"Immich geo field {field} must be a string or null"
            )
            error.code = "invalid_immich_geo_metadata"
            raise error
        return value if value.strip() else None

    @staticmethod
    def _draft(
        predicate: str,
        value: str,
        locator: str,
    ) -> StatementDraft:
        return StatementDraft(
            predicate=predicate,
            value=TypedStatementValue(
                StatementValueType.STRING,
                value,
            ),
            evidence=Evidence(
                EvidenceSourceKind.PROVIDER_METADATA,
                locator,
            ),
            confidence=None,
        )

    def extract(self, resource: EnrichmentResource) -> ObservationBatch:
        source = self._selected_source(resource)
        values = self._relevant(source)
        labels = {
            key: self._label(values[key], key)
            for _, key, _ in self._LABELS
        }
        drafts: tuple[StatementDraft, ...] = ()
        if self._valid_coordinates(
            values["latitude"],
            values["longitude"],
        ):
            drafts = tuple(
                self._draft(predicate, labels[key], locator)
                for predicate, key, locator in self._LABELS
                if labels[key] is not None
            )
        return ObservationBatch(
            subject_resource_ref=resource.resource_ref,
            generator=self.generator,
            covered_predicates=self.covered_predicates,
            input_fingerprint=self.input_fingerprint(resource),
            statements=drafts,
        )
