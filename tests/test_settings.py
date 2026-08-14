import pytest
from pydantic import ValidationError

from pdi.config import (
    Settings,
    load_immich_settings,
    load_nextcloud_settings,
)


def _set_required_environment(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE__URL",
        "postgresql+psycopg://user:password@db/pdi",
    )
    monkeypatch.setenv(
        "NEXTCLOUD__URL",
        "https://nextcloud.example",
    )
    monkeypatch.setenv(
        "NEXTCLOUD__USER",
        "nextcloud-user",
    )
    monkeypatch.setenv(
        "NEXTCLOUD__PASSWORD",
        "nextcloud-password",
    )
    monkeypatch.delenv("IMMICH__URL", raising=False)
    monkeypatch.delenv("IMMICH__API_KEY", raising=False)


def test_settings_loads_immich_environment(
    monkeypatch,
) -> None:
    _set_required_environment(monkeypatch)
    monkeypatch.setenv(
        "IMMICH__URL",
        "https://immich.example",
    )
    monkeypatch.setenv(
        "IMMICH__API_KEY",
        "immich-api-key",
    )

    settings = Settings(_env_file=None)

    assert settings.immich is not None
    assert settings.immich.url == "https://immich.example"
    assert settings.immich.api_key == "immich-api-key"


def test_settings_allows_nextcloud_without_immich(
    monkeypatch,
) -> None:
    _set_required_environment(monkeypatch)

    settings = Settings(_env_file=None)

    assert settings.immich is None


def test_settings_rejects_partial_immich_configuration(
    monkeypatch,
) -> None:
    _set_required_environment(monkeypatch)
    monkeypatch.setenv(
        "IMMICH__URL",
        "https://immich.example",
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_load_immich_settings_does_not_require_other_configuration(
    monkeypatch,
) -> None:
    for name in (
        "DATABASE__URL",
        "NEXTCLOUD__URL",
        "NEXTCLOUD__USER",
        "NEXTCLOUD__PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("IMMICH__URL", "https://immich.example")
    monkeypatch.setenv("IMMICH__API_KEY", "immich-api-key")

    settings = load_immich_settings()

    assert settings.url == "https://immich.example"
    assert settings.api_key == "immich-api-key"


def test_load_immich_settings_fails_clearly_when_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv("IMMICH__URL", raising=False)
    monkeypatch.delenv("IMMICH__API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="IMMICH__URL.*IMMICH__API_KEY"):
        load_immich_settings()


def test_load_nextcloud_settings_does_not_require_other_configuration(
    monkeypatch,
) -> None:
    monkeypatch.delenv("DATABASE__URL", raising=False)
    monkeypatch.delenv("IMMICH__URL", raising=False)
    monkeypatch.delenv("IMMICH__API_KEY", raising=False)
    monkeypatch.setenv("NEXTCLOUD__URL", "https://nextcloud.example")
    monkeypatch.setenv("NEXTCLOUD__USER", "nextcloud-user")
    monkeypatch.setenv(
        "NEXTCLOUD__PASSWORD",
        "nextcloud-password",
    )

    settings = load_nextcloud_settings()

    assert settings.url == "https://nextcloud.example"
    assert settings.user == "nextcloud-user"
    assert settings.password == "nextcloud-password"


def test_load_nextcloud_settings_fails_clearly_when_missing(
    monkeypatch,
) -> None:
    for name in (
        "NEXTCLOUD__URL",
        "NEXTCLOUD__USER",
        "NEXTCLOUD__PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(
        RuntimeError,
        match="NEXTCLOUD__URL.*NEXTCLOUD__USER.*NEXTCLOUD__PASSWORD",
    ):
        load_nextcloud_settings()
