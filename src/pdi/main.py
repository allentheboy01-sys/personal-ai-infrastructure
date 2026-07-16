import logging

from pdi.adapters.nextcloud.adapter import NextcloudAdapter
from pdi.config import Settings
from pdi.database import create_postgres_engine
from pdi.engine import SyncEngine
from pdi.identity import Matcher
from pdi.observability import configure_logging
from pdi.repository import PostgreSQLRepository


logger = logging.getLogger(__name__)


def main() -> None:
    settings = Settings()

    configure_logging(
        settings.logging.level,
    )

    logger.info("PDI starting")

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

    try:
        sync_engine.sync_once()
    except Exception:
        logger.exception("PDI sync failed")
        raise

    logger.info("PDI stopped successfully")


if __name__ == "__main__":
    main()