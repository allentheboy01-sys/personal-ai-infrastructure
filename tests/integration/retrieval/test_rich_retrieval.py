import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from mcp import Client
import pytest
from sqlalchemy import Connection, Engine, event

from pdi.database import create_postgres_engine
from pdi.query import format_resource_ref
from pdi.repository import PostgreSQLRepository
from pdi.repository.orm.asset import AssetORM
from pdi.repository.orm.asset_source import AssetSourceORM
from pdi.repository.orm.blob import BlobORM
from pdi.repository.orm.observation import ResourceStatementORM
from pdi.rich_retrieval import (
    InvalidRichRetrievalStateError,
    ObservationTextPrimary,
    ProviderSemanticPrimary,
    RichFilters,
    RichRetrievalService,
)
from pdi.retrieval import ProviderRetrievalHit, RetrievalService
from pdi_mcp.bootstrap import create_runtime_server
from tests.integration.database_guard import require_safe_test_database_url


ROOT = Path(__file__).resolve().parents[3]
CAPTURED = datetime(2025, 6, 1, 12, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class RichData:
    token: str
    ocr_ref: str
    document_ref: str
    multi_ref: str
    missing_ref: str
    ocr_locator: str
    multi_locator: str
    missing_locator: str
    literal_text: str
    document_text: str
    historical_text: str


def _alembic_config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def _statement(
    asset_id: UUID,
    predicate: str,
    *,
    string_value: str | None = None,
    datetime_value: datetime | None = None,
    current: bool = True,
    generator: str = "rich-test",
) -> dict[str, object]:
    return {
        "id": uuid4(),
        "subject_asset_id": asset_id,
        "predicate": predicate,
        "value_type": (
            "datetime" if datetime_value is not None else "string"
        ),
        "string_value": string_value,
        "integer_value": None,
        "float_value": None,
        "boolean_value": None,
        "datetime_value": datetime_value,
        "resource_value_asset_id": None,
        "generator_type": "integration_test",
        "generator_name": generator,
        "generator_version": "1",
        "source_kind": "resource_content",
        "source_locator": "integration-test-fixture",
        "confidence": None,
        "created_at": datetime(2026, 8, 15, tzinfo=UTC),
        "is_current": current,
    }


@pytest.fixture(scope="module")
def rich_context():
    database_url = require_safe_test_database_url()
    engine = create_postgres_engine(database_url)
    with engine.connect() as connection:
        command.upgrade(_alembic_config(connection), "head")

    token = uuid4().hex
    now = datetime(2026, 8, 15, tzinfo=UTC)
    ocr_id, document_id, historical_id, multi_id, missing_id = (
        uuid4() for _ in range(5)
    )
    asset_specs = (
        (ocr_id, "A Rich OCR.jpg"),
        (document_id, "B Rich Document.pdf"),
        (historical_id, "C Rich Historical.jpg"),
        (multi_id, "D Rich Multi.jpg"),
        (missing_id, "E Rich Missing.jpg"),
    )
    blob_specs = [
        (uuid4(), ocr_id, "image/jpeg"),
        (uuid4(), document_id, "application/pdf"),
        (uuid4(), historical_id, "image/jpeg"),
        (uuid4(), multi_id, "text/markdown"),
        (uuid4(), multi_id, "image/jpeg"),
        (uuid4(), missing_id, "image/jpeg"),
    ]
    ocr_locator = f"rich-ocr-{token}"
    multi_locator = f"rich-multi-{token}"
    missing_locator = f"rich-missing-{token}"
    source_specs = (
        (uuid4(), blob_specs[0][0], "immich", ocr_locator, "/photos/a.jpg"),
        (uuid4(), blob_specs[1][0], "nextcloud", f"rich-doc-{token}", "/docs/a.pdf"),
        (uuid4(), blob_specs[2][0], "immich", f"rich-history-{token}", "/photos/history.jpg"),
        (uuid4(), blob_specs[3][0], "nextcloud", f"rich-multi-nc-{token}", "/docs/multi.md"),
        (uuid4(), blob_specs[4][0], "immich", multi_locator, "/photos/multi.jpg"),
        (uuid4(), blob_specs[5][0], "immich", missing_locator, "/photos/missing.jpg"),
    )
    literal_text = (
        f"CamBridge-{token} percent-{token}% "
        f"underscore-{token}_ backslash-{token}\\ "
        f"Unicode-你好-{token}"
    )
    document_text = f"Machine Learning {token} handbook"
    historical_text = f"HistoricOnly {token}"
    statement_rows = (
        _statement(
            ocr_id,
            "media.ocr_text",
            string_value=literal_text,
        ),
        _statement(
            ocr_id,
            "media.captured_at",
            datetime_value=CAPTURED,
        ),
        _statement(
            ocr_id,
            "media.camera_make",
            string_value="Original Camera Co.",
        ),
        _statement(
            document_id,
            "document.text_excerpt",
            string_value=document_text,
        ),
        _statement(
            historical_id,
            "media.ocr_text",
            string_value=historical_text,
            current=False,
        ),
        _statement(
            multi_id,
            "media.ocr_text",
            string_value=literal_text,
        ),
        _statement(
            multi_id,
            "media.captured_at",
            datetime_value=CAPTURED,
        ),
    )

    with engine.begin() as connection:
        connection.execute(AssetORM.__table__.insert(), [
            {
                "id": asset_id,
                "title": title,
                "metadata": {},
                "created_at": now,
                "updated_at": now,
            }
            for asset_id, title in asset_specs
        ])
        connection.execute(BlobORM.__table__.insert(), [
            {
                "id": blob_id,
                "asset_id": asset_id,
                "hash": f"rich-{token}-{index}",
                "size": 100,
                "mime_type": mime_type,
            }
            for index, (blob_id, asset_id, mime_type) in enumerate(
                blob_specs
            )
        ])
        connection.execute(AssetSourceORM.__table__.insert(), [
            {
                "id": source_id,
                "blob_id": blob_id,
                "provider": provider,
                "external_id": locator,
                "path": path,
                "name": path.rsplit("/", 1)[-1],
                "version_tag": "1",
                "metadata": {},
                "is_active": True,
                "deleted_at": None,
            }
            for source_id, blob_id, provider, locator, path in source_specs
        ])
        connection.execute(
            ResourceStatementORM.__table__.insert(),
            list(statement_rows),
        )

    data = RichData(
        token=token,
        ocr_ref=format_resource_ref(ocr_id),
        document_ref=format_resource_ref(document_id),
        multi_ref=format_resource_ref(multi_id),
        missing_ref=format_resource_ref(missing_id),
        ocr_locator=ocr_locator,
        multi_locator=multi_locator,
        missing_locator=missing_locator,
        literal_text=literal_text,
        document_text=document_text,
        historical_text=historical_text,
    )
    try:
        yield engine, PostgreSQLRepository(engine), data
    finally:
        asset_ids = [asset_id for asset_id, _ in asset_specs]
        with engine.begin() as connection:
            connection.execute(
                ResourceStatementORM.__table__.delete().where(
                    ResourceStatementORM.subject_asset_id.in_(asset_ids)
                )
            )
            connection.execute(
                AssetSourceORM.__table__.delete().where(
                    AssetSourceORM.id.in_([
                        spec[0] for spec in source_specs
                    ])
                )
            )
            connection.execute(
                BlobORM.__table__.delete().where(
                    BlobORM.id.in_([spec[0] for spec in blob_specs])
                )
            )
            connection.execute(
                AssetORM.__table__.delete().where(
                    AssetORM.id.in_(asset_ids)
                )
            )
        engine.dispose()


def test_observation_text_is_literal_current_and_deterministic(
    rich_context,
) -> None:
    _, repository, data = rich_context
    service = RichRetrievalService(repository)

    case_result = service.retrieve_resources(
        primary=ObservationTextPrimary(
            "observation_text",
            f"cambridge-{data.token}",
            "media.ocr_text",
        ),
        limit=20,
    )
    assert [hit.resource.resource_ref for hit in case_result.hits] == [
        data.ocr_ref,
        data.multi_ref,
    ]
    assert [hit.source_rank for hit in case_result.hits] == [1, 2]

    for literal in (
        f"percent-{data.token}%",
        f"underscore-{data.token}_",
        f"backslash-{data.token}\\",
        f"unicode-你好-{data.token}",
    ):
        result = service.retrieve_resources(
            primary=ObservationTextPrimary(
                "observation_text",
                literal,
                "media.ocr_text",
            )
        )
        assert len(result.hits) == 2

    historical = service.retrieve_resources(
        primary=ObservationTextPrimary(
            "observation_text",
            data.historical_text,
            "media.ocr_text",
        )
    )
    assert historical.hits == ()

    document = service.retrieve_resources(
        primary=ObservationTextPrimary(
            "observation_text",
            f"machine learning {data.token}",
            "document.text_excerpt",
        )
    )
    assert [hit.resource.resource_ref for hit in document.hits] == [
        data.document_ref
    ]


class StaticProviderAdapter:
    provider = "immich"

    def __init__(self, hits: tuple[ProviderRetrievalHit, ...]) -> None:
        self.hits = hits
        self.calls: list[tuple[str, int]] = []

    def search_resources(self, *, query: str, limit: int):
        self.calls.append((query, limit))
        return self.hits


def test_provider_candidates_use_batch_filters_same_source_and_keep_rank(
    rich_context,
) -> None:
    engine, repository, data = rich_context
    adapter = StaticProviderAdapter((
        ProviderRetrievalHit("immich", data.ocr_locator, 1),
        ProviderRetrievalHit("immich", f"unmapped-{data.token}", 2),
        ProviderRetrievalHit("immich", data.multi_locator, 4),
        ProviderRetrievalHit("immich", data.missing_locator, 5),
    ))
    service = RichRetrievalService(
        repository,
        RetrievalService(adapter, repository),
    )

    select_statements: list[str] = []

    def record_select(_, __, statement, *args) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_select)
    try:
        result = service.retrieve_resources(
            primary=ProviderSemanticPrimary(
                "provider_semantic",
                "car",
                "immich",
            ),
            filters=RichFilters(
                provider="immich",
                mime_category="image",
                captured_from=datetime(2025, 1, 1, tzinfo=UTC),
                captured_to=datetime(2026, 1, 1, tzinfo=UTC),
                required_predicates=("media.ocr_text",),
            ),
            limit=20,
        )
    finally:
        event.remove(engine, "before_cursor_execute", record_select)

    assert adapter.calls == [("car", 50)]
    assert [hit.resource.resource_ref for hit in result.hits] == [
        data.ocr_ref,
        data.multi_ref,
    ]
    assert [hit.source_rank for hit in result.hits] == [1, 4]
    assert result.unmapped_hit_count == 1
    assert result.hits[0].captured_at == CAPTURED
    assert len(select_statements) == 5

    cross_source = service.retrieve_resources(
        primary=ProviderSemanticPrimary(
            "provider_semantic",
            "car",
            "immich",
        ),
        filters=RichFilters(
            provider="nextcloud",
            mime_type="image/jpeg",
        ),
    )
    assert data.multi_ref not in {
        hit.resource.resource_ref for hit in cross_source.hits
    }

    same_source = service.retrieve_resources(
        primary=ProviderSemanticPrimary(
            "provider_semantic",
            "car",
            "immich",
        ),
        filters=RichFilters(
            provider="immich",
            mime_type="image/jpeg",
        ),
    )
    assert data.multi_ref in {
        hit.resource.resource_ref for hit in same_source.hits
    }


def test_multiple_current_captured_claims_fail_whole_request(
    rich_context,
) -> None:
    engine, repository, data = rich_context
    asset_id = UUID(data.ocr_ref.removeprefix("pdi:resource:"))
    extra_id = uuid4()
    row = _statement(
        asset_id,
        "media.captured_at",
        datetime_value=datetime(2024, 1, 1, tzinfo=UTC),
        generator="rich-test-second",
    )
    row["id"] = extra_id
    with engine.begin() as connection:
        connection.execute(ResourceStatementORM.__table__.insert(), row)
    try:
        with pytest.raises(InvalidRichRetrievalStateError):
            RichRetrievalService(repository).retrieve_resources(
                primary=ObservationTextPrimary(
                    "observation_text",
                    f"cambridge-{data.token}",
                    "media.ocr_text",
                ),
                filters=RichFilters(captured_from=datetime.min.replace(
                    tzinfo=UTC
                )),
            )
    finally:
        with engine.begin() as connection:
            connection.execute(
                ResourceStatementORM.__table__.delete().where(
                    ResourceStatementORM.id == extra_id
                )
            )


def test_mcp_in_memory_client_reaches_real_postgresql_without_leakage(
    rich_context,
) -> None:
    _, _, data = rich_context
    server = create_runtime_server(require_safe_test_database_url())

    async def exercise():
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            result = await client.call_tool(
                "pdi_rich_retrieve_resources",
                {
                    "primary": {
                        "kind": "observation_text",
                        "query": f"machine learning {data.token}",
                        "predicate": "document.text_excerpt",
                    },
                    "filters": {
                        "provider": "nextcloud",
                        "mime_type": "application/pdf",
                    },
                    "limit": 20,
                },
            )
        return tools, result

    tools, result = asyncio.run(exercise())
    assert len(tools) == 7
    payload = result.structured_content
    assert payload["ok"] is True
    assert [
        hit["resource"]["resource_ref"] for hit in payload["hits"]
    ] == [data.document_ref]
    encoded = json.dumps(payload)
    assert data.document_text not in encoded
    assert data.token not in encoded
    def all_keys(value):
        if isinstance(value, dict):
            return set(value) | {
                key
                for nested in value.values()
                for key in all_keys(nested)
            }
        if isinstance(value, list):
            return {
                key
                for nested in value
                for key in all_keys(nested)
            }
        return set()

    keys = all_keys(payload)
    for private_name in (
        "asset_id",
        "blob_id",
        "source_id",
        "external_id",
        "provider_locator",
        "metadata",
        "raw",
    ):
        assert private_name not in keys
