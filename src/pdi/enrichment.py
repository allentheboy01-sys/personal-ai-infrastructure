import argparse
from collections.abc import Sequence

from pdi.adapters.nextcloud.adapter import NextcloudAdapter
from pdi.config.settings import (
    load_database_url,
    load_immich_settings,
    load_nextcloud_settings,
)
from pdi.database import create_postgres_engine
from pdi.observation import (
    EnrichmentWorker,
    FileMetadataExtractor,
    ImmichMetadataExtractor,
    ImmichOCRExtractor,
    ImmichOCRReader,
    NextcloudContentReader,
    NextcloudDOCXExtractor,
    NextcloudODTExtractor,
    NextcloudPDFExtractor,
    NextcloudTextExtractor,
    PostgreSQLObservationRepository,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one bounded PDI enrichment batch."
    )
    parser.add_argument(
        "--extractor",
        choices=(
            "immich-metadata",
            "immich-ocr",
            "file-metadata",
            "nextcloud-text",
            "nextcloud-documents",
        ),
        default="immich-metadata",
        help=(
            "Extractor to run; defaults to immich-metadata so existing "
            "scheduled metadata enrichment is unchanged."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Maximum Resources to attempt (default: 100).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive")
    engine = create_postgres_engine(load_database_url())
    try:
        provider = "immich"
        if args.extractor == "immich-metadata":
            extractor = ImmichMetadataExtractor()
        elif args.extractor == "file-metadata":
            extractor = FileMetadataExtractor()
            provider = extractor.discovery_providers
        elif args.extractor == "immich-ocr":
            extractor = ImmichOCRExtractor(
                ImmichOCRReader(load_immich_settings())
            )
        elif args.extractor == "nextcloud-text":
            settings = load_nextcloud_settings()
            adapter = NextcloudAdapter(
                settings.url,
                settings.user,
                settings.password,
            )
            extractor = NextcloudTextExtractor(
                NextcloudContentReader(adapter)
            )
            provider = "nextcloud"
        else:
            extractor = None
            provider = "nextcloud"
        repository = PostgreSQLObservationRepository(engine)
        if args.extractor == "nextcloud-documents":
            settings = load_nextcloud_settings()
            reader = NextcloudContentReader(
                NextcloudAdapter(
                    settings.url,
                    settings.user,
                    settings.password,
                )
            )
            results = []
            for document_extractor in (
                NextcloudPDFExtractor(reader),
                NextcloudODTExtractor(reader),
                NextcloudDOCXExtractor(reader),
            ):
                result = EnrichmentWorker(
                    repository,
                    document_extractor,
                    provider="nextcloud",
                ).run_once(batch_size=args.batch_size)
                results.append(result)
                print(
                    f"{document_extractor.generator.generator_name} "
                    "finished: "
                    f"discovered={result.discovered} "
                    f"processed={result.processed} "
                    f"skipped={result.skipped} "
                    f"failed={result.failed} "
                    f"statement_writes={result.statement_writes} "
                    f"deactivated={result.deactivated_statements}"
                )
            return 0 if all(result.failed == 0 for result in results) else 1
        if provider == "immich":
            worker = EnrichmentWorker(repository, extractor)
        else:
            worker = EnrichmentWorker(
                repository,
                extractor,
                provider=provider,
            )
        result = worker.run_once(batch_size=args.batch_size)
        print(
            "Enrichment finished: "
            f"discovered={result.discovered} "
            f"processed={result.processed} "
            f"skipped={result.skipped} "
            f"failed={result.failed} "
            f"statement_writes={result.statement_writes} "
            f"deactivated={result.deactivated_statements}"
        )
        return 0 if result.failed == 0 else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
