from pdi.adapters.nextcloud.adapter import NextcloudAdapter
from pdi.config import Settings
from pdi.database import create_postgres_engine
from pdi.engine import SyncEngine
from pdi.identity import Matcher
from pdi.repository import PostgreSQLRepository


def main() -> None:
    settings = Settings()

    adapter = NextcloudAdapter(
        base_url=settings.nextcloud.url,
        username=settings.nextcloud.user,
        password=settings.nextcloud.password,
    )

    db_engine = create_postgres_engine(
        settings.database.url,
    )

    repository = PostgreSQLRepository(
        db_engine,
    )

    matcher = Matcher()

    sync_engine = SyncEngine(
        adapter=adapter,
        matcher=matcher,
        repository=repository,
    )

    sync_engine.sync_once()

    print("Sync finished.")


if __name__ == "__main__":
    main()