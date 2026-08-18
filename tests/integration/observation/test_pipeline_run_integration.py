from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from pdi.data_status import PipelineRunRepository, PipelineStatus
from pdi.operational import run_formal_pipeline
from tests.integration.database_guard import require_safe_test_database_url


@pytest.fixture
def formal_enrichment_context(monkeypatch):
    database_url = require_safe_test_database_url()
    engine = create_engine(database_url, poolclass=NullPool)
    config = Config("alembic.ini")
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM resource_enrichments"))
        connection.execute(text("DELETE FROM resource_statements"))
        connection.execute(text("DELETE FROM pipeline_runs"))
        connection.execute(text("DELETE FROM asset_sources"))
        connection.execute(text("DELETE FROM blobs"))
        connection.execute(text("DELETE FROM assets"))
    monkeypatch.setenv("DATABASE__URL", database_url)
    try:
        yield engine, database_url
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM resource_enrichments"))
            connection.execute(text("DELETE FROM resource_statements"))
            connection.execute(text("DELETE FROM pipeline_runs"))
            connection.execute(text("DELETE FROM asset_sources"))
            connection.execute(text("DELETE FROM blobs"))
            connection.execute(text("DELETE FROM assets"))
        engine.dispose()


def test_formal_noop_and_resource_failure_follow_existing_cli_exit_contract(
    formal_enrichment_context,
    tmp_path,
) -> None:
    engine, database_url = formal_enrichment_context
    assert run_formal_pipeline(
        "enrichment.immich_metadata",
        lock_timeout=0,
        lock_path=tmp_path / "formal.lock",
        engine_factory=lambda url: engine,
        database_url_loader=lambda: database_url,
    ) == 0

    asset_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO assets (id,title,metadata,created_at,updated_at) "
                "VALUES (:id,'ambiguous','{}'::jsonb,now(),now())"
            ),
            {"id": asset_id},
        )
        for number in (1, 2):
            blob_id = uuid4()
            connection.execute(
                text(
                    "INSERT INTO blobs (id,asset_id,hash,size,mime_type) "
                    "VALUES (:id,:asset_id,:hash,1,'image/jpeg')"
                ),
                {"id": blob_id, "asset_id": asset_id, "hash": f"hash-{number}"},
            )
            connection.execute(
                text(
                    "INSERT INTO asset_sources "
                    "(id,blob_id,provider,external_id,metadata,is_active) "
                    "VALUES (:id,:blob_id,'immich',:external_id,'{}'::jsonb,true)"
                ),
                {
                    "id": uuid4(),
                    "blob_id": blob_id,
                    "external_id": f"ambiguous-{number}",
                },
            )

    assert run_formal_pipeline(
        "enrichment.immich_metadata",
        lock_timeout=0,
        lock_path=tmp_path / "formal.lock",
        engine_factory=lambda url: engine,
        database_url_loader=lambda: database_url,
    ) == 1

    repository = PipelineRunRepository(engine)
    latest = repository.get_latest_runs(["enrichment.immich_metadata"])
    assert latest["enrichment.immich_metadata"].status is PipelineStatus.FAILED
    assert repository.get_last_successes(
        ["enrichment.immich_metadata"]
    )["enrichment.immich_metadata"] is not None
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT status FROM resource_enrichments "
                "WHERE extractor_name='immich_metadata'"
            )
        ).scalar_one() == "failed"
