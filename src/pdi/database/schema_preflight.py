from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.engine import Inspector
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.sqltypes import (
    BigInteger,
    Boolean,
    DateTime,
    Text,
)

from pdi.config.settings import load_database_url


BASELINE_REVISION = "7452797c95ca"

_EXPECTED_TABLES = {
    "assets",
    "blobs",
    "asset_sources",
}


class SchemaPreflightError(RuntimeError):
    """The target database does not match the approved V0.1 schema."""


@dataclass(frozen=True)
class ColumnSpec:
    type_: type
    nullable: bool
    default: str | None = None


_COLUMNS: dict[str, dict[str, ColumnSpec]] = {
    "assets": {
        "id": ColumnSpec(PG_UUID, False),
        "title": ColumnSpec(Text, False),
        "metadata": ColumnSpec(JSONB, False, "'{}'::jsonb"),
        "created_at": ColumnSpec(DateTime, False),
        "updated_at": ColumnSpec(DateTime, False),
    },
    "blobs": {
        "id": ColumnSpec(PG_UUID, False),
        "asset_id": ColumnSpec(PG_UUID, False),
        "hash": ColumnSpec(Text, False),
        "size": ColumnSpec(BigInteger, True),
        "mime_type": ColumnSpec(Text, True),
    },
    "asset_sources": {
        "id": ColumnSpec(PG_UUID, False),
        "blob_id": ColumnSpec(PG_UUID, False),
        "provider": ColumnSpec(Text, False),
        "external_id": ColumnSpec(Text, False),
        "path": ColumnSpec(Text, True),
        "name": ColumnSpec(Text, True),
        "version_tag": ColumnSpec(Text, True),
        "metadata": ColumnSpec(JSONB, False, "'{}'::jsonb"),
        "is_active": ColumnSpec(Boolean, False, "true"),
        "deleted_at": ColumnSpec(DateTime, True),
    },
}

_PRIMARY_KEYS = {
    "assets": ("id",),
    "blobs": ("id",),
    "asset_sources": ("id",),
}

_FOREIGN_KEYS = {
    "blobs": {
        (
            ("asset_id",),
            None,
            "assets",
            ("id",),
            "RESTRICT",
            None,
        ),
    },
    "asset_sources": {
        (
            ("blob_id",),
            None,
            "blobs",
            ("id",),
            "RESTRICT",
            None,
        ),
    },
}

_UNIQUE_CONSTRAINTS = {
    "assets": set(),
    "blobs": {
        ("asset_id", "hash"),
    },
    "asset_sources": {
        ("provider", "external_id"),
    },
}


def _normalize_default(value: object) -> str | None:
    if value is None:
        return None

    normalized = re.sub(r"\s+", "", str(value)).lower()

    while normalized.startswith("(") and normalized.endswith(")"):
        normalized = normalized[1:-1]

    if normalized in {"true", "true::boolean"}:
        return "true"

    return normalized


def _column_map(
    inspector: Inspector,
    table_name: str,
) -> dict[str, Mapping[str, Any]]:
    return {
        column["name"]: column
        for column in inspector.get_columns(table_name)
    }


def _check_columns(
    inspector: Inspector,
    differences: list[str],
) -> None:
    for table_name, expected_columns in _COLUMNS.items():
        actual_columns = _column_map(inspector, table_name)

        if set(actual_columns) != set(expected_columns):
            differences.append(
                f"{table_name} columns: expected "
                f"{sorted(expected_columns)}, got "
                f"{sorted(actual_columns)}"
            )
            continue

        for name, expected in expected_columns.items():
            actual = actual_columns[name]

            if not isinstance(actual["type"], expected.type_):
                differences.append(
                    f"{table_name}.{name} type: expected "
                    f"{expected.type_.__name__}, got "
                    f"{type(actual['type']).__name__}"
                )

            if actual["nullable"] is not expected.nullable:
                differences.append(
                    f"{table_name}.{name} nullable: expected "
                    f"{expected.nullable}, got {actual['nullable']}"
                )

            actual_default = _normalize_default(actual.get("default"))

            if actual_default != expected.default:
                differences.append(
                    f"{table_name}.{name} default: expected "
                    f"{expected.default!r}, got {actual_default!r}"
                )


def _check_primary_keys(
    inspector: Inspector,
    differences: list[str],
) -> None:
    for table_name, expected in _PRIMARY_KEYS.items():
        actual = tuple(
            inspector.get_pk_constraint(table_name)
            .get("constrained_columns", ())
        )

        if actual != expected:
            differences.append(
                f"{table_name} primary key: expected "
                f"{expected}, got {actual}"
            )


def foreign_key_semantics(
    foreign_key: Mapping[str, Any],
) -> tuple[
    tuple,
    str | None,
    str | None,
    tuple,
    str | None,
    str | None,
]:
    """Normalize a reflected foreign key without its internal name."""

    options = foreign_key.get("options") or {}
    referred_schema = foreign_key.get("referred_schema")
    onupdate = str(options.get("onupdate", "")).upper() or None

    if referred_schema == "public":
        referred_schema = None

    if onupdate == "NO ACTION":
        onupdate = None

    return (
        tuple(foreign_key.get("constrained_columns") or ()),
        referred_schema,
        foreign_key.get("referred_table"),
        tuple(foreign_key.get("referred_columns") or ()),
        str(options.get("ondelete", "")).upper() or None,
        onupdate,
    )


def unique_constraint_semantics(
    constraint: Mapping[str, Any],
) -> tuple:
    """Normalize a reflected unique constraint without its internal name."""

    return tuple(constraint.get("column_names") or ())


def _format_foreign_key_semantics(
    semantics: tuple,
) -> str:
    (
        local_columns,
        referred_schema,
        referred_table,
        referred_columns,
        ondelete,
        onupdate,
    ) = semantics

    return (
        f"local_columns={local_columns}, "
        f"referred_schema={referred_schema!r}, "
        f"referred_table={referred_table!r}, "
        f"referred_columns={referred_columns}, "
        f"ondelete={ondelete!r}, "
        f"onupdate={onupdate!r}"
    )


def _check_foreign_keys(
    inspector: Inspector,
    differences: list[str],
) -> None:
    for table_name, expected in _FOREIGN_KEYS.items():
        actual = {
            foreign_key_semantics(foreign_key)
            for foreign_key in inspector.get_foreign_keys(table_name)
        }

        missing = expected - actual
        unexpected = actual - expected

        if missing:
            differences.append(
                f"{table_name} foreign keys missing semantics: "
                + "; ".join(
                    _format_foreign_key_semantics(semantics)
                    for semantics in sorted(missing, key=repr)
                )
            )

        if unexpected:
            differences.append(
                f"{table_name} foreign keys unexpected semantics: "
                + "; ".join(
                    _format_foreign_key_semantics(semantics)
                    for semantics in sorted(unexpected, key=repr)
                )
            )


def _check_unique_constraints(
    inspector: Inspector,
    differences: list[str],
) -> None:
    for table_name, expected in _UNIQUE_CONSTRAINTS.items():
        actual = {
            unique_constraint_semantics(constraint)
            for constraint
            in inspector.get_unique_constraints(table_name)
        }

        missing = expected - actual
        unexpected = actual - expected

        if missing:
            differences.append(
                f"{table_name} unique constraints missing columns: "
                f"{sorted(missing, key=repr)}"
            )

        if unexpected:
            differences.append(
                f"{table_name} unique constraints unexpected columns: "
                f"{sorted(unexpected, key=repr)}"
            )


def _check_blob_index(
    inspector: Inspector,
    differences: list[str],
) -> None:
    matching = [
        index
        for index in inspector.get_indexes("blobs")
        if index.get("name") == "ix_blobs_hash"
    ]

    if len(matching) != 1:
        differences.append(
            "blobs index ix_blobs_hash: expected exactly one"
        )
        return

    index = matching[0]

    if tuple(index.get("column_names") or ()) != ("hash",):
        differences.append(
            "ix_blobs_hash columns: expected ('hash',), got "
            f"{tuple(index.get('column_names') or ())}"
        )

    if bool(index.get("unique")):
        differences.append(
            "ix_blobs_hash unique: expected False, got True"
        )


def collect_v0_1_schema_differences(
    connection: Connection,
    *,
    require_unversioned: bool = True,
) -> list[str]:
    """Return a read-only difference summary for V0.1 adoption."""

    differences: list[str] = []
    inspector = inspect(connection)

    current_schema = connection.execute(
        text("SELECT current_schema()")
    ).scalar_one()

    if current_schema != "public":
        differences.append(
            "current schema: expected 'public', "
            f"got {current_schema!r}"
        )

    actual_tables = set(inspector.get_table_names())
    expected_tables = set(_EXPECTED_TABLES)

    if not require_unversioned:
        expected_tables.add("alembic_version")

    if actual_tables != expected_tables:
        differences.append(
            f"tables: expected {sorted(expected_tables)}, "
            f"got {sorted(actual_tables)}"
        )

    if not _EXPECTED_TABLES.issubset(actual_tables):
        return differences

    if require_unversioned and "alembic_version" in actual_tables:
        differences.append(
            "alembic_version already exists; database is not "
            "an unversioned V0.1 candidate"
        )

    _check_columns(inspector, differences)
    _check_primary_keys(inspector, differences)
    _check_foreign_keys(inspector, differences)
    _check_unique_constraints(inspector, differences)
    _check_blob_index(inspector, differences)

    return differences


def assert_v0_1_schema(
    connection: Connection,
    *,
    require_unversioned: bool = True,
) -> None:
    """Raise when the target is not the exact approved V0.1 schema."""

    differences = collect_v0_1_schema_differences(
        connection,
        require_unversioned=require_unversioned,
    )

    if differences:
        summary = "\n".join(
            f"- {difference}"
            for difference in differences
        )
        raise SchemaPreflightError(
            "V0.1 schema preflight failed:\n"
            f"{summary}"
        )


def run_preflight(engine: Engine) -> None:
    """Run the V0.1 adoption preflight without modifying the database."""

    with engine.connect() as connection:
        assert_v0_1_schema(connection)


def main(argv: Sequence[str] | None = None) -> int:
    del argv

    engine = create_engine(
        load_database_url(),
        poolclass=NullPool,
    )

    try:
        run_preflight(engine)
    finally:
        engine.dispose()

    print(
        "V0.1 schema preflight passed; "
        f"safe to review stamp {BASELINE_REVISION}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
