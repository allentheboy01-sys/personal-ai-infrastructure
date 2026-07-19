import os

import pytest
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


def database_target_identity(url: URL) -> tuple[str, int, str]:
    """Return a credential-independent PostgreSQL target identity."""

    if url.get_backend_name() != "postgresql":
        raise ValueError("database URL must use PostgreSQL")

    host = (url.host or "").strip().lower()

    if not host:
        raise ValueError("database URL must include a host")

    database = (url.database or "").strip()

    if not database:
        raise ValueError("database URL must include a database name")

    return (
        host,
        url.port or 5432,
        database,
    )


def parse_safe_test_database_url(raw_url: str) -> URL:
    """Parse and validate an explicitly destructive test target."""

    try:
        test_url = make_url(raw_url)
    except ArgumentError as error:
        raise ValueError(
            "PDI_TEST_DATABASE_URL is not a valid SQLAlchemy URL"
        ) from error

    _, _, database = database_target_identity(test_url)

    if not database.endswith("_test"):
        raise ValueError(
            "PDI_TEST_DATABASE_URL database name must end with _test"
        )

    return test_url


def require_safe_test_database_url() -> str:
    """Return an explicitly isolated PostgreSQL test URL or skip."""

    raw_url = os.environ.get("PDI_TEST_DATABASE_URL")

    if not raw_url:
        pytest.skip(
            "PDI_TEST_DATABASE_URL is required for PostgreSQL "
            "integration tests"
        )

    try:
        test_url = parse_safe_test_database_url(raw_url)
        test_identity = database_target_identity(test_url)
    except ValueError as error:
        pytest.skip(str(error))

    production_url = os.environ.get("DATABASE__URL")

    if production_url:
        try:
            parsed_production_url = make_url(production_url)
            production_identity = database_target_identity(
                parsed_production_url
            )
        except (ArgumentError, ValueError):
            pytest.skip(
                "DATABASE__URL is invalid; test database isolation "
                "cannot be confirmed"
            )

        if test_identity == production_identity:
            pytest.skip(
                "PDI_TEST_DATABASE_URL must not target the same "
                "host, port, and database as DATABASE__URL"
            )

    return raw_url
