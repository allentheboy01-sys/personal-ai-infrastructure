from __future__ import annotations

import pytest

import pdi.cli as cli
from pdi.config import PDIConfigurationError


def test_sync_routes_to_existing_application_entrypoint(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "pdi.main.main",
        lambda argv: calls.append(list(argv)),
    )

    assert cli.main(["sync", "--provider", "immich"]) == 0
    assert calls == [["--provider", "immich"]]


def test_implicit_sync_routes_without_selecting_gmail(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "pdi.main.main",
        lambda argv: calls.append(list(argv)),
    )

    assert cli.main(["sync"]) == 0
    assert calls == [[]]


def test_mcp_routes_to_existing_stdio_entrypoint(monkeypatch) -> None:
    calls: list[None] = []
    monkeypatch.setattr(
        "pdi_mcp.bootstrap.main",
        lambda: calls.append(None),
    )

    assert cli.main(["mcp"]) == 0
    assert calls == [None]


def test_configuration_failure_is_sanitized(monkeypatch, capsys) -> None:
    def fail(argv) -> None:
        raise PDIConfigurationError(
            "Nextcloud configuration is required for: "
            "pdi sync --provider nextcloud"
        )

    monkeypatch.setattr("pdi.main.main", fail)

    assert cli.main(["sync", "--provider", "nextcloud"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Nextcloud configuration is required" in captured.err
    assert "Traceback" not in captured.err


def test_real_selected_provider_configuration_failure_is_clear(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "DATABASE__URL",
        "postgresql+psycopg://user:password@db/pdi",
    )
    for name in (
        "NEXTCLOUD__URL",
        "NEXTCLOUD__USER",
        "NEXTCLOUD__PASSWORD",
        "IMMICH__URL",
        "IMMICH__API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    assert cli.main(["sync", "--provider", "nextcloud"]) == 2
    captured = capsys.readouterr()
    assert "NEXTCLOUD__URL" in captured.err
    assert "Traceback" not in captured.err


def test_cli_rejects_unknown_commands_before_composition(capsys) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["unknown"])

    assert error.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_module_entrypoints_remain_available() -> None:
    from pdi.main import main as sync_main
    from pdi_mcp.bootstrap import main as mcp_main

    assert callable(sync_main)
    assert callable(mcp_main)
