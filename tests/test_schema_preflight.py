from pdi.database.schema_preflight import (
    foreign_key_semantics,
    unique_constraint_semantics,
)


def _foreign_key(
    *,
    name: str,
    referred_columns: tuple[str, ...] = ("id",),
    ondelete: str = "RESTRICT",
) -> dict:
    return {
        "name": name,
        "constrained_columns": ["asset_id"],
        "referred_schema": None,
        "referred_table": "assets",
        "referred_columns": list(referred_columns),
        "options": {
            "ondelete": ondelete,
        },
    }


def test_foreign_key_names_do_not_affect_semantics() -> None:
    assert foreign_key_semantics(
        _foreign_key(name="fk_blobs_asset")
    ) == foreign_key_semantics(
        _foreign_key(name="blobs_asset_id_fkey")
    )


def test_foreign_key_ondelete_affects_semantics() -> None:
    assert foreign_key_semantics(
        _foreign_key(
            name="fk_blobs_asset",
            ondelete="RESTRICT",
        )
    ) != foreign_key_semantics(
        _foreign_key(
            name="fk_blobs_asset",
            ondelete="CASCADE",
        )
    )


def test_foreign_key_referred_columns_affect_semantics() -> None:
    assert foreign_key_semantics(
        _foreign_key(name="fk_blobs_asset")
    ) != foreign_key_semantics(
        _foreign_key(
            name="fk_blobs_asset",
            referred_columns=("external_id",),
        )
    )


def test_unique_names_do_not_affect_semantics() -> None:
    expected = {
        "name": "uq_blobs_asset_hash",
        "column_names": ["asset_id", "hash"],
    }
    generated = {
        "name": "blobs_asset_id_hash_key",
        "column_names": ["asset_id", "hash"],
    }

    assert unique_constraint_semantics(
        expected
    ) == unique_constraint_semantics(generated)


def test_unique_columns_affect_semantics() -> None:
    expected = {
        "name": "uq_blobs_asset_hash",
        "column_names": ["asset_id", "hash"],
    }
    drifted = {
        "name": "uq_blobs_asset_hash",
        "column_names": ["hash"],
    }

    assert unique_constraint_semantics(
        expected
    ) != unique_constraint_semantics(drifted)
