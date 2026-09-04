from types import SimpleNamespace

import pytest

import pdi.main as pdi_main
from pdi.adapters.immich import ImmichAdapter
from pdi.adapters.nextcloud.adapter import NextcloudAdapter


def _settings(
    *,
    nextcloud_configured: bool = True,
    immich_configured: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        database=SimpleNamespace(
            url="postgresql+psycopg://user:password@db/pdi",
        ),
        nextcloud=(
            SimpleNamespace(
                url="https://nextcloud.example",
                user="nextcloud-user",
                password="nextcloud-password",
            )
            if nextcloud_configured
            else None
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
    engine = SimpleNamespace(disposed=False)
    engine.dispose = lambda: setattr(engine, "disposed", True)
    repository = object()
    matcher = object()
    state_repository = object()
    sync_calls: list[dict[str, object]] = []

    class FakeSyncEngine:
        def __init__(
            self,
            *,
            adapter,
            matcher,
            repository,
            sync_state_repository=None,
        ) -> None:
            self.adapter = adapter
            sync_calls.append(
                {
                    "adapter": adapter,
                    "matcher": matcher,
                    "repository": repository,
                    "sync_state_repository": sync_state_repository,
                }
            )

        def sync_once(self) -> None:
            sync_calls[-1]["synced"] = True

    monkeypatch.setattr(
        pdi_main,
        "load_settings",
        lambda selected_provider=None: settings,
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
    monkeypatch.setattr(
        pdi_main,
        "PostgreSQLProviderSyncStateRepository",
        lambda configured_engine: state_repository,
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
        "load_settings",
        lambda selected_provider=None: pytest.fail(
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
        match="Immich configuration is required.*pdi sync --provider immich",
    ):
        pdi_main.main(["--provider", "immich"])

    assert sync_calls == []


def test_main_fails_clearly_when_selected_nextcloud_is_not_configured(
    monkeypatch,
) -> None:
    sync_calls, _, _ = _configure_composition_fakes(
        monkeypatch,
        _settings(nextcloud_configured=False),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Nextcloud configuration is required.*"
            "pdi sync --provider nextcloud"
        ),
    ):
        pdi_main.main(["--provider", "nextcloud"])

    assert sync_calls == []


def test_main_fails_when_no_implicit_provider_is_configured(
    monkeypatch,
) -> None:
    sync_calls, _, _ = _configure_composition_fakes(
        monkeypatch,
        _settings(
            nextcloud_configured=False,
            immich_configured=False,
        ),
    )

    with pytest.raises(RuntimeError, match="No eligible Provider"):
        pdi_main.main([])

    assert sync_calls == []


def test_main_implicit_sync_never_constructs_gmail(monkeypatch) -> None:
    sync_calls, _, _ = _configure_composition_fakes(
        monkeypatch,
        _settings(),
    )
    monkeypatch.setattr(
        pdi_main,
        "GmailAdapter",
        lambda **kwargs: pytest.fail(
            "Gmail must remain explicit-only"
        ),
    )

    pdi_main.main([])

    assert len(sync_calls) == 2


@pytest.mark.parametrize(
    ("argv", "expected_count"),
    [
        (["--operation", "full"], 2),
        (["--provider", "nextcloud", "--operation", "full"], 1),
        (["--provider", "immich", "--operation", "full"], 1),
        (["--provider", "gmail", "--operation", "full"], 1),
    ],
)
def test_explicit_full_preserves_sync_once_behavior(
    monkeypatch, argv, expected_count
) -> None:
    sync_calls, _, _ = _configure_composition_fakes(
        monkeypatch,
        _settings(),
    )
    monkeypatch.setattr(
        pdi_main,
        "PostgreSQLProviderSyncStateRepository",
        lambda engine: pytest.fail(
            "Full sync must not construct incremental state persistence"
        ),
    )
    pdi_main.main(argv)
    assert len(sync_calls) == expected_count
    assert all(call["synced"] is True for call in sync_calls)
    assert all(
        call["sync_state_repository"] is None for call in sync_calls
    )


@pytest.mark.parametrize("provider", ["nextcloud", "immich"])
@pytest.mark.parametrize(
    ("operation", "method"),
    [
        ("incremental", "run_incremental"),
        ("bootstrap", "bootstrap"),
        ("recover", "recover"),
    ],
)
def test_main_dispatches_one_non_full_provider_operation(
    monkeypatch, provider, operation, method
) -> None:
    sync_calls, _, _ = _configure_composition_fakes(
        monkeypatch,
        _settings(),
    )
    service_calls = []

    class FakeService:
        def __init__(self, adapter, sync_engine, state_repository):
            service_calls.append(
                ("init", adapter.provider_name, sync_engine, state_repository)
            )

        def run_incremental(self):
            service_calls.append("run_incremental")

        def bootstrap(self):
            service_calls.append("bootstrap")

        def recover(self):
            service_calls.append("recover")

    module = (
        "pdi.adapters.nextcloud.incremental.NextcloudActivityIncrementalSync"
        if provider == "nextcloud"
        else "pdi.adapters.immich.incremental.ImmichIncrementalSync"
    )
    monkeypatch.setattr(module, FakeService)
    pdi_main.main([
        "--provider", provider, "--operation", operation
    ])

    assert len(sync_calls) == 1
    assert sync_calls[0].get("synced") is None
    assert sync_calls[0]["sync_state_repository"] is not None
    assert service_calls[0][0:2] == ("init", provider)
    assert service_calls[1] == method


@pytest.mark.parametrize(
    "argv",
    [
        ["--operation", "incremental"],
        ["--operation", "bootstrap"],
        ["--operation", "recover"],
        ["--provider", "gmail", "--operation", "incremental"],
        ["--provider", "gmail", "--operation", "bootstrap"],
        ["--provider", "gmail", "--operation", "recover"],
    ],
)
def test_main_rejects_non_full_before_loading_settings(
    monkeypatch, capsys, argv
) -> None:
    monkeypatch.setattr(
        pdi_main,
        "load_settings",
        lambda selected_provider=None: pytest.fail(
            "Settings must not load for an invalid operation combination"
        ),
    )
    with pytest.raises(SystemExit) as error:
        pdi_main.main(argv)
    assert error.value.code == 2
    assert "non-full operations require" in capsys.readouterr().err


def test_main_rejects_unknown_operation_before_loading_settings(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        pdi_main,
        "load_settings",
        lambda selected_provider=None: pytest.fail(
            "Settings must not load for an unknown operation"
        ),
    )
    with pytest.raises(SystemExit) as error:
        pdi_main.main(["--provider", "nextcloud", "--operation", "unknown"])
    assert error.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
