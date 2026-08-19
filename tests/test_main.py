from types import SimpleNamespace

import pytest

import pdi.main as pdi_main
from pdi.adapters.immich import ImmichAdapter
from pdi.adapters.nextcloud.adapter import NextcloudAdapter


def _settings(
    *,
    immich_configured: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        database=SimpleNamespace(
            url="postgresql+psycopg://user:password@db/pdi",
        ),
        nextcloud=SimpleNamespace(
            url="https://nextcloud.example",
            user="nextcloud-user",
            password="nextcloud-password",
        ),
        immich=(
            SimpleNamespace(
                url="https://immich.example",
                api_key="immich-api-key",
            )
            if immich_configured
            else None
        ),
        gmail=SimpleNamespace(
            token_file="/private/test-token.json",
        ),
        logging=SimpleNamespace(
            level="INFO",
        ),
    )


def _configure_composition_fakes(
    monkeypatch,
    settings: SimpleNamespace,
) -> tuple[list[dict[str, object]], object, object]:
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

    return sync_calls, repository, matcher


def test_main_syncs_all_configured_providers_in_stable_order(
    monkeypatch,
) -> None:
    sync_calls, repository, matcher = _configure_composition_fakes(
        monkeypatch,
        _settings(),
    )

    pdi_main.main([])

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


def test_main_nextcloud_selection_never_constructs_immich(
    monkeypatch,
) -> None:
    sync_calls, _, _ = _configure_composition_fakes(
        monkeypatch,
        _settings(),
    )
    monkeypatch.setattr(
        pdi_main,
        "ImmichAdapter",
        lambda **kwargs: pytest.fail(
            "Immich must not be constructed for nextcloud-only sync"
        ),
    )

    pdi_main.main(["--provider", "nextcloud"])

    assert len(sync_calls) == 1
    assert isinstance(
        sync_calls[0]["adapter"],
        NextcloudAdapter,
    )


def test_main_gmail_selection_uses_explicit_read_only_adapter(
    monkeypatch,
) -> None:
    sync_calls, _, _ = _configure_composition_fakes(
        monkeypatch,
        _settings(),
    )
    sentinel = object()
    seen = {}

    def fake_gmail_adapter(*, token_file):
        seen["token_file"] = token_file
        return sentinel

    monkeypatch.setattr(pdi_main, "GmailAdapter", fake_gmail_adapter)
    pdi_main.main(["--provider", "gmail"])
    assert seen == {"token_file": "/private/test-token.json"}
    assert len(sync_calls) == 1
    assert sync_calls[0]["adapter"] is sentinel


def test_main_immich_selection_never_constructs_nextcloud(
    monkeypatch,
) -> None:
    sync_calls, _, _ = _configure_composition_fakes(
        monkeypatch,
        _settings(),
    )
    monkeypatch.setattr(
        pdi_main,
        "NextcloudAdapter",
        lambda **kwargs: pytest.fail(
            "Nextcloud must not be constructed for immich-only sync"
        ),
    )

    pdi_main.main(["--provider", "immich"])

    assert len(sync_calls) == 1
    assert isinstance(
        sync_calls[0]["adapter"],
        ImmichAdapter,
    )


def test_main_rejects_invalid_provider_before_loading_settings(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        pdi_main,
        "Settings",
        lambda: pytest.fail(
            "Settings must not load for an invalid provider"
        ),
    )

    with pytest.raises(SystemExit) as error:
        pdi_main.main(["--provider", "unknown"])

    assert error.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_main_fails_clearly_when_selected_immich_is_not_configured(
    monkeypatch,
) -> None:
    sync_calls, _, _ = _configure_composition_fakes(
        monkeypatch,
        _settings(immich_configured=False),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "--provider immich requires IMMICH__URL "
            "and IMMICH__API_KEY"
        ),
    ):
        pdi_main.main(["--provider", "immich"])

    assert sync_calls == []
