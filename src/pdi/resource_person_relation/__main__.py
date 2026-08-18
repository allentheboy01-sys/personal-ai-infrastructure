import sys
import time

from pdi.config.settings import load_database_url, load_immich_settings
from pdi.database.postgres import create_postgres_engine

from .immich import ImmichResourcePersonRelationAdapter
from .repository import ResourcePersonRelationRepository
from .service import ResourcePersonRelationSyncService


def main() -> int:
    started_at = time.perf_counter()
    engine = None
    try:
        settings = load_immich_settings()
        engine = create_postgres_engine(load_database_url())
        service = ResourcePersonRelationSyncService(
            ImmichResourcePersonRelationAdapter(
                settings.url,
                settings.api_key,
            ),
            ResourcePersonRelationRepository(engine),
        )
        result = service.sync_once()
    except Exception:
        print("resource_person_relation_sync status=failed", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()

    duration = time.perf_counter() - started_at
    print(
        "resource_person_relation_sync status=completed "
        f"observed={result.observed} "
        f"created={result.created} "
        f"unchanged={result.unchanged} "
        f"reactivated={result.reactivated} "
        f"inactivated={result.inactivated} "
        f"skipped_unmapped={result.skipped_unmapped} "
        f"duration={duration:.2f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
