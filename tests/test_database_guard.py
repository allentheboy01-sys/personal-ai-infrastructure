import pytest
from sqlalchemy.engine import make_url

from tests.integration.database_guard import (
    database_target_identity,
    parse_safe_test_database_url,
)


def test_identity_ignores_username() -> None:
    first = make_url(
        "postgresql+psycopg://first:secret@db.example/pdi_test"
    )
    second = make_url(
        "postgresql+psycopg://second:secret@db.example/pdi_test"
    )

    assert database_target_identity(
        first
    ) == database_target_identity(second)


def test_identity_ignores_password() -> None:
    first = make_url(
        "postgresql+psycopg://user:secret@db.example/pdi_test"
    )
    second = make_url(
        "postgresql+psycopg://user:different@db.example/pdi_test"
    )

    assert database_target_identity(
        first
    ) == database_target_identity(second)


def test_identity_uses_default_postgresql_port() -> None:
    implicit = make_url(
        "postgresql+psycopg://user@db.example/pdi_test"
    )
    explicit = make_url(
        "postgresql+psycopg://user@db.example:5432/pdi_test"
    )

    assert database_target_identity(
        implicit
    ) == database_target_identity(explicit)


def test_identity_normalizes_host_case() -> None:
    uppercase = make_url(
        "postgresql+psycopg://user@DB.EXAMPLE/pdi_test"
    )
    lowercase = make_url(
        "postgresql+psycopg://user@db.example/pdi_test"
    )

    assert database_target_identity(
        uppercase
    ) == database_target_identity(lowercase)


def test_different_databases_have_different_identity() -> None:
    first = make_url(
        "postgresql+psycopg://user@db.example/first_test"
    )
    second = make_url(
        "postgresql+psycopg://user@db.example/second_test"
    )

    assert database_target_identity(
        first
    ) != database_target_identity(second)


def test_non_postgresql_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="must use PostgreSQL"):
        parse_safe_test_database_url("sqlite:///pdi_test")


def test_missing_database_name_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="must include a database name",
    ):
        parse_safe_test_database_url(
            "postgresql+psycopg://user@db.example"
        )


def test_missing_host_is_rejected() -> None:
    with pytest.raises(ValueError, match="must include a host"):
        parse_safe_test_database_url(
            "postgresql+psycopg:///pdi_test"
        )


def test_non_test_database_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="must end with _test"):
        parse_safe_test_database_url(
            "postgresql+psycopg://user@db.example/pdi"
        )
