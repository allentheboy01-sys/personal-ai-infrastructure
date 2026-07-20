from types import SimpleNamespace

import pdi.main as pdi_main
from pdi.adapters.immich import ImmichAdapter
from pdi.adapters.nextcloud.adapter import NextcloudAdapter


def test_main_syncs_nextcloud_and_immich_with_shared_core(
    monkeypatch,
) -> None:
    settings = SimpleNamespace(
        database=SimpleNamespace(
            url="postgresql+psycopg://user:password@db/pdi",
        ),
        nextcloud=SimpleNamespace(
            url="https://nextcloud.example",
            user="nextcloud-user",
            password="nextcloud-password",
        ),
        immich=SimpleNamespace(
            url="https://immich.example",
            api_key="immich-api-key",
        ),
        logging=SimpleNamespace(
            level="INFO",
        ),
    )
    engine = object()
    repository = object()
    matcher = object()
    sync_calls: list[dict[str, object]] = []

    class FakeSyncEngine:
        def __init__(
            self,
            *,
            adapter,
            matcher,
            repository,
        ) -> None:
            self.adapter = adapter
            sync_calls.append(
                {
                    "adapter": adapter,
                    "matcher": matcher,
                    "repository": repository,
                }
            )

        def sync_once(self) -> None:
            sync_calls[-1]["synced"] = True

    monkeypatch.setattr(
        pdi_main,
        "Settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        pdi_main,
        "configure_logging",
        lambda level: None,
    )
    monkeypatch.setattr(
        pdi_main,
        "create_postgres_engine",
        lambda url: engine,
    )
    monkeypatch.setattr(
        pdi_main,
        "PostgreSQLRepository",
        lambda configured_engine: repository,
    )
    monkeypatch.setattr(
        pdi_main,
        "Matcher",
        lambda: matcher,
    )
    monkeypatch.setattr(
        pdi_main,
        "SyncEngine",
        FakeSyncEngine,
    )

    pdi_main.main()

    assert len(sync_calls) == 2
    assert isinstance(
        sync_calls[0]["adapter"],
        NextcloudAdapter,
    )
    assert isinstance(
        sync_calls[1]["adapter"],
        ImmichAdapter,
    )
    assert all(
        call["matcher"] is matcher
        and call["repository"] is repository
        and call["synced"] is True
        for call in sync_calls
    )
