from dataclasses import dataclass

from pdi.observation import GeneratorIdentity

from .models import PipelineKind


@dataclass(frozen=True)
class PipelineDefinition:
    pipeline_key: str
    kind: PipelineKind
    dependencies: tuple[str, ...] = ()
    enrichment_generators: tuple[GeneratorIdentity, ...] = ()


PIPELINES = (
    PipelineDefinition(
        "provider.nextcloud.sync",
        PipelineKind.PROVIDER_SYNC,
    ),
    PipelineDefinition(
        "provider.immich.sync",
        PipelineKind.PROVIDER_SYNC,
    ),
    PipelineDefinition(
        "provider.gmail.sync",
        PipelineKind.PROVIDER_SYNC,
    ),
    PipelineDefinition(
        "enrichment.nextcloud_text",
        PipelineKind.ENRICHMENT,
        ("provider.nextcloud.sync",),
        (GeneratorIdentity("deterministic_extractor", "nextcloud_text", "1"),),
    ),
    PipelineDefinition(
        "enrichment.nextcloud_documents",
        PipelineKind.ENRICHMENT,
        ("provider.nextcloud.sync",),
        (
            GeneratorIdentity("deterministic_extractor", "nextcloud_pdf", "1"),
            GeneratorIdentity("deterministic_extractor", "nextcloud_odt", "1"),
            GeneratorIdentity("deterministic_extractor", "nextcloud_docx", "1"),
        ),
    ),
    PipelineDefinition(
        "enrichment.file_metadata",
        PipelineKind.ENRICHMENT,
        ("provider.nextcloud.sync", "provider.immich.sync"),
        (GeneratorIdentity("deterministic_extractor", "file_metadata", "1"),),
    ),
    PipelineDefinition(
        "enrichment.immich_geo",
        PipelineKind.ENRICHMENT,
        ("provider.immich.sync",),
        (GeneratorIdentity("deterministic_extractor", "immich_geo", "1"),),
    ),
    PipelineDefinition(
        "enrichment.immich_metadata",
        PipelineKind.ENRICHMENT,
        ("provider.immich.sync",),
        (GeneratorIdentity("deterministic_extractor", "immich_metadata", "1"),),
    ),
    PipelineDefinition(
        "enrichment.immich_ocr",
        PipelineKind.ENRICHMENT,
        ("provider.immich.sync",),
        (GeneratorIdentity("provider_native_ml", "immich_ocr", "1"),),
    ),
    PipelineDefinition(
        "enrichment.gmail_metadata",
        PipelineKind.ENRICHMENT,
        ("provider.gmail.sync",),
        (GeneratorIdentity("deterministic_extractor", "gmail_metadata", "1"),),
    ),
)


def validate_registry(
    pipelines: tuple[PipelineDefinition, ...],
) -> None:
    by_key = {pipeline.pipeline_key: pipeline for pipeline in pipelines}
    if len(by_key) != len(pipelines):
        raise ValueError("pipeline keys must be unique")
    for pipeline in pipelines:
        if not pipeline.pipeline_key.strip():
            raise ValueError("pipeline key must be non-empty")
        for dependency in pipeline.dependencies:
            if dependency == pipeline.pipeline_key:
                raise ValueError("pipeline cannot depend on itself")
            if dependency not in by_key:
                raise ValueError(f"unknown pipeline dependency: {dependency}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visiting:
            raise ValueError("pipeline dependency cycle detected")
        if key in visited:
            return
        visiting.add(key)
        for dependency in by_key[key].dependencies:
            visit(dependency)
        visiting.remove(key)
        visited.add(key)

    for key in by_key:
        visit(key)


validate_registry(PIPELINES)
PIPELINE_REGISTRY = {pipeline.pipeline_key: pipeline for pipeline in PIPELINES}
