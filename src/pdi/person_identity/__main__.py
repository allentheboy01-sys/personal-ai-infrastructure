import sys
import time

from pdi.config.settings import load_database_url, load_immich_settings
from pdi.database.postgres import create_postgres_engine

from .immich import ImmichEnumerablePeopleAdapter
from .repository import PersonRepository
from .service import PersonSyncService


def main() -> int:
    started_at = time.perf_counter()
    engine = None
    try:
        settings = load_immich_settings()
        engine = create_postgres_engine(load_database_url())
        service = PersonSyncService(
            ImmichEnumerablePeopleAdapter(settings.url, settings.api_key),
            PersonRepository(engine),
        )
        result = service.sync_once()
    except Exception:
        print("person_sync status=failed", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()

    duration = time.perf_counter() - started_at
    print(
        "person_sync status=completed "
        f"enumerated={result.discovered} "
        f"created_persons={result.created} "
        f"created_sources={result.created} "
        f"reactivated_sources={result.reactivated} "
        f"inactivated_sources={result.inactivated} "
        f"unchanged_sources={result.existing} "
        f"duration={duration:.2f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
