import argparse
import logging
from collections.abc import Sequence

from pdi.adapters.base import Adapter
from pdi.adapters.gmail import GmailAdapter
from pdi.adapters.immich import ImmichAdapter
from pdi.adapters.nextcloud.adapter import NextcloudAdapter
from pdi.config import PDIConfigurationError, Settings, load_settings
from pdi.database import create_postgres_engine
from pdi.engine import SyncEngine
from pdi.identity import Matcher
from pdi.observability import configure_logging
from pdi.repository import PostgreSQLRepository


logger = logging.getLogger(__name__)


def _parse_args(
    argv: Sequence[str] | None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synchronize configured PDI providers.",
    )
    parser.add_argument(
        "--provider",
        choices=("nextcloud", "immich", "gmail"),
        help=(
            "Synchronize only one provider. "
            "Without this option, configured Nextcloud and Immich providers "
            "are synchronized; Gmail remains explicit-only."
        ),
    )
    return parser.parse_args(argv)


def _build_adapters(
    settings: Settings,
    selected_provider: str | None,
) -> list[Adapter]:
    adapters: list[Adapter] = []

    if selected_provider in {None, "nextcloud"}:
        if settings.nextcloud is None:
            if selected_provider == "nextcloud":
                raise PDIConfigurationError(
                    "Nextcloud configuration is required for: "
                    "pdi sync --provider nextcloud"
                )
            logger.info("Nextcloud is not configured; skipping provider")
        else:
            adapters.append(
                NextcloudAdapter(
                    base_url=settings.nextcloud.url,
                    username=settings.nextcloud.user,
                    password=settings.nextcloud.password,
                )
            )

    if selected_provider in {None, "immich"}:
        if settings.immich is None:
            if selected_provider == "immich":
                raise PDIConfigurationError(
                    "Immich configuration is required for: "
                    "pdi sync --provider immich"
                )

            logger.info(
                "Immich is not configured; skipping provider"
            )
        else:
            adapters.append(
                ImmichAdapter(
                    base_url=settings.immich.url,
                    api_key=settings.immich.api_key,
                )
            )

    # Gmail remains an explicit development/pilot sync. It is not included
    # in the existing implicit all-provider production path.
    if selected_provider == "gmail":
        adapters.append(
            GmailAdapter(token_file=settings.gmail.token_file)
        )

    if not adapters:
        raise PDIConfigurationError(
            "No eligible Provider is configured; configure Nextcloud or "
            "Immich, or select Gmail explicitly"
        )

    return adapters


def main(
    argv: Sequence[str] | None = None,
) -> None:
    args = _parse_args(argv)
    settings = load_settings(args.provider)

    configure_logging(
        settings.logging.level,
    )

    logger.info("PDI starting")

    adapters = _build_adapters(
        settings,
        selected_provider=args.provider,
    )

    db_engine = create_postgres_engine(
        settings.database.url,
    )

    repository = PostgreSQLRepository(
        db_engine,
    )

    matcher = Matcher()

    try:
        for adapter in adapters:
            sync_engine = SyncEngine(
                adapter=adapter,
                matcher=matcher,
                repository=repository,
            )
            sync_engine.sync_once()
    except Exception:
        logger.exception("PDI sync failed")
        raise

    logger.info("PDI stopped successfully")


if __name__ == "__main__":
    main()
