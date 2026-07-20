import pytest
from pydantic import ValidationError

from pdi.config import Settings


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
