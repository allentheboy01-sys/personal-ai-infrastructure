import argparse
from collections.abc import Sequence

from pdi.config.settings import load_database_url
from pdi.database import create_postgres_engine
from pdi.observation import (
    EnrichmentWorker,
    ImmichMetadataExtractor,
    PostgreSQLObservationRepository,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one bounded PDI enrichment batch."
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
        worker = EnrichmentWorker(
            PostgreSQLObservationRepository(engine),
            ImmichMetadataExtractor(),
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
