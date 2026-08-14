import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from mcp import Client
from sqlalchemy import create_engine, text

from pdi.observation import (
    Evidence,
    EvidenceSourceKind,
    GeneratorIdentity,
    MAX_STORED_TEXT_BYTES,
    ObservationBatch,
    PostgreSQLObservationRepository,
    StatementDraft,
    StatementValueType,
    TypedStatementValue,
)
from pdi.query import format_resource_ref
from pdi_mcp.bootstrap import create_runtime_server
from tests.integration.database_guard import require_safe_test_database_url


ROOT = Path(__file__).resolve().parents[3]


def test_mcp_observation_tool_reads_real_postgresql_without_internal_ids() -> None:
    database_url = require_safe_test_database_url()
    engine = create_engine(database_url)
    with engine.connect() as connection:
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    asset_id = uuid4()
    now = datetime(2026, 8, 13, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO assets (id,title,metadata,created_at,updated_at) "
            "VALUES (:id,'observation-mcp','{}'::jsonb,:now,:now)"
        ), {"id": asset_id, "now": now})
    resource_ref = format_resource_ref(asset_id)
    repository = PostgreSQLObservationRepository(engine)
    repository.publish(ObservationBatch(
        resource_ref,
        GeneratorIdentity("provider_native_ml", "immich_ocr", "1"),
        ("media.ocr_text",),
        "1" * 64,
        (StatementDraft(
            "media.ocr_text",
            TypedStatementValue(StatementValueType.STRING, "a" * 8192),
            Evidence(
                EvidenceSourceKind.PROVIDER_METADATA,
                "immich.api.asset_ocr",
            ),
        ),),
    ), completed_at=now)
    repository.publish(ObservationBatch(
        resource_ref,
        GeneratorIdentity(
            "deterministic_extractor",
            "nextcloud_text",
            "1",
        ),
        ("document.text_excerpt",),
        "2" * 64,
        (StatementDraft(
            "document.text_excerpt",
            TypedStatementValue(
                StatementValueType.STRING,
                "d" * MAX_STORED_TEXT_BYTES,
            ),
            Evidence(
                EvidenceSourceKind.RESOURCE_CONTENT,
                "nextcloud.webdav.content",
            ),
        ),),
    ), completed_at=now)

    async def exercise() -> None:
        async with Client(create_runtime_server(database_url)) as client:
            tools = (await client.list_tools()).tools
            result = await client.call_tool(
                "pdi_get_resource_observations",
                {
                    "resource_ref": resource_ref,
                    "predicate": "media.ocr_text",
                },
            )
            document_result = await client.call_tool(
                "pdi_get_resource_observations",
                {
                    "resource_ref": resource_ref,
                    "predicate": "document.text_excerpt",
                },
            )
        assert len(tools) == 6
        observation = result.structured_content["observations"][0]
        assert observation["predicate"] == "media.ocr_text"
        assert observation["value"] == "a" * 8192
        assert len(observation["value"].encode("utf-8")) == 8192
        assert observation["source_locator"] == "immich.api.asset_ocr"
        payload = str(result.structured_content)
        assert str(asset_id) not in payload.replace(resource_ref, "")
        assert "external_id" not in payload
        assert "provider_locator" not in payload
        assert "raw" not in payload
        document = document_result.structured_content[
            "observations"
        ][0]
        assert document["predicate"] == "document.text_excerpt"
        assert len(document["value"].encode("utf-8")) == (
            MAX_STORED_TEXT_BYTES
        )
        assert document["generator_type"] == "deterministic_extractor"
        assert document["generator_name"] == "nextcloud_text"
        assert document["generator_version"] == "1"
        assert document["source_kind"] == "resource_content"
        assert document["source_locator"] == (
            "nextcloud.webdav.content"
        )
        document_payload = str(document_result.structured_content)
        for internal in (
            "href",
            "source_id",
            "external_id",
            "blob_id",
            "provider_locator",
            "raw",
        ):
            assert internal not in document_payload

    try:
        asyncio.run(exercise())
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM resource_enrichments WHERE subject_asset_id=:id"), {"id": asset_id})
            connection.execute(text("DELETE FROM resource_statements WHERE subject_asset_id=:id"), {"id": asset_id})
            connection.execute(text("DELETE FROM assets WHERE id=:id"), {"id": asset_id})
        engine.dispose()
