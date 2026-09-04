import argparse
import logging
from collections.abc import Sequence
from enum import StrEnum

from pdi.adapters.base import Adapter
from pdi.adapters.gmail import GmailAdapter
from pdi.config import PDIConfigurationError, Settings, load_settings
from pdi.database import create_postgres_engine
from pdi.engine import SyncEngine
from pdi.identity import Matcher
from pdi.observability import configure_logging
from pdi.repository import PostgreSQLRepository
from pdi.sync_state import PostgreSQLProviderSyncStateRepository
from pdi.adapters.immich.adapter import ImmichAdapter
from pdi.adapters.nextcloud.adapter import NextcloudAdapter


logger = logging.getLogger(__name__)


class SyncOperation(StrEnum):
    FULL = "full"
    INCREMENTAL = "incremental"
    BOOTSTRAP = "bootstrap"
    RECOVER = "recover"


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
    parser.add_argument(
        "--operation",
        choices=tuple(operation.value for operation in SyncOperation),
        default=SyncOperation.FULL.value,
        help="Provider sync operation; defaults to full.",
    )
    args = parser.parse_args(argv)
    operation = SyncOperation(args.operation)
    if (
        operation is not SyncOperation.FULL
        and args.provider not in {"nextcloud", "immich"}
    ):
        parser.error(
            "non-full operations require --provider nextcloud or immich"
        )
    args.operation = operation
    return args


def _run_operation(
    adapter: Adapter,
    operation: SyncOperation,
    sync_engine: SyncEngine,
    sync_state_repository: PostgreSQLProviderSyncStateRepository | None,
) -> None:
    if operation is SyncOperation.FULL:
        sync_engine.sync_once()
        return
    if sync_state_repository is None:
        raise RuntimeError("Non-full sync requires Provider state persistence")
    if adapter.provider_name == "nextcloud":
        from pdi.adapters.nextcloud.incremental import (
            NextcloudActivityIncrementalSync,
        )

        service = NextcloudActivityIncrementalSync(
            adapter,
            sync_engine,
            sync_state_repository,
        )
    elif adapter.provider_name == "immich":
        from pdi.adapters.immich.incremental import ImmichIncrementalSync

        service = ImmichIncrementalSync(
            adapter,
            sync_engine,
            sync_state_repository,
        )
    else:
        raise PDIConfigurationError(
            f"Provider {adapter.provider_name} supports full sync only"
        )
    if operation is SyncOperation.INCREMENTAL:
        service.run_incremental()
    elif operation is SyncOperation.BOOTSTRAP:
        service.bootstrap()
    else:
        service.recover()


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
    sync_state_repository = (
        None
        if args.operation is SyncOperation.FULL
        else PostgreSQLProviderSyncStateRepository(db_engine)
    )

    try:
        for adapter in adapters:
            engine_arguments = {
                "adapter": adapter,
                "matcher": matcher,
                "repository": repository,
            }
            if sync_state_repository is not None:
                engine_arguments["sync_state_repository"] = (
                    sync_state_repository
                )
            sync_engine = SyncEngine(
                **engine_arguments,
            )
            _run_operation(
                adapter,
                args.operation,
                sync_engine,
                sync_state_repository,
            )
    except Exception:
        logger.exception("PDI sync failed")
        raise
    finally:
        db_engine.dispose()

    logger.info("PDI stopped successfully")


if __name__ == "__main__":
    main()
