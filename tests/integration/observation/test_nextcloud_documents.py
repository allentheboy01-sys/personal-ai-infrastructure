import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from mcp import Client
import pytest
from sqlalchemy import Engine, create_engine, select, text

from pdi.observation import (
    EnrichmentWorker,
    Evidence,
    EvidenceSourceKind,
    GeneratorIdentity,
    NextcloudDOCXExtractor,
    NextcloudODTExtractor,
    NextcloudPDFExtractor,
    ObservationBatch,
    PostgreSQLObservationRepository,
    StatementDraft,
    StatementValueType,
    TypedStatementValue,
)
from pdi.observation.nextcloud_documents import DOCUMENT_GENERATOR_FAMILY
from pdi.query import format_resource_ref
from pdi.repository.orm.observation import (
    ResourceStatementORM,
)
from pdi_mcp.bootstrap import create_runtime_server
from tests.integration.database_guard import require_safe_test_database_url
from tests.test_nextcloud_documents import (
    DOCX_MIME,
    ODT_MIME,
    PDF_MIME,
    _docx,
    _odt,
    _pdf,
)


ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 8, 15, 12, tzinfo=UTC)


@dataclass(frozen=True)
class FormatCase:
    extractor: type
    mime_type: str
    name: str
    content: Callable[[str], bytes]
    empty_content: Callable[[], bytes]


FORMATS = (
    FormatCase(
        NextcloudPDFExtractor,
        PDF_MIME,
        "document.pdf",
        lambda value: _pdf([value]),
        lambda: _pdf([None]),
    ),
    FormatCase(
        NextcloudODTExtractor,
        ODT_MIME,
        "document.odt",
        lambda value: _odt(f"<text:p>{value}</text:p>"),
        lambda: _odt("<text:p> </text:p>"),
    ),
    FormatCase(
        NextcloudDOCXExtractor,
        DOCX_MIME,
        "document.docx",
        lambda value: _docx(
            f"<w:p><w:r><w:t>{value}</w:t></w:r></w:p>"
        ),
        lambda: _docx("<w:p/>"),
    ),
)


@dataclass
class CreatedResource:
    asset_id: UUID
    blob_id: UUID
    source_id: UUID
    resource_ref: str
    locator: str
    content: bytes


@pytest.fixture(scope="module")
def engine() -> Engine:
    configured = create_engine(require_safe_test_database_url())
    with configured.connect() as connection:
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    try:
        yield configured
    finally:
        configured.dispose()


@pytest.fixture
def resource_factory(engine):
    assets: list[UUID] = []
    blobs: list[UUID] = []
    sources: list[UUID] = []

    def create(
        content: bytes,
        *,
        mime_type: str,
        name: str,
        active: bool = True,
    ) -> CreatedResource:
        asset_id = uuid4()
        blob_id = uuid4()
        source_id = uuid4()
        locator = f"document-test-{uuid4().hex}"
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO assets "
                    "(id,resource_type,title,metadata,created_at,updated_at) "
                    "VALUES (:id,'file','document-test','{}'::jsonb,:now,:now)"
                ),
                {"id": asset_id, "now": NOW},
            )
            connection.execute(
                text(
                    "INSERT INTO blobs "
                    "(id,asset_id,hash,size,mime_type) "
                    "VALUES (:id,:asset,:hash,:size,:mime)"
                ),
                {
                    "id": blob_id,
                    "asset": asset_id,
                    "hash": sha256(content).hexdigest(),
                    "size": len(content),
                    "mime": mime_type,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO asset_sources "
                    "(id,blob_id,provider,external_id,path,name,version_tag,"
                    "metadata,is_active,deleted_at) VALUES "
                    "(:id,:blob,'nextcloud',:locator,:path,:name,'etag-1',"
                    "'{}'::jsonb,:active,:deleted)"
                ),
                {
                    "id": source_id,
                    "blob": blob_id,
                    "locator": locator,
                    "path": f"test-only/{name}",
                    "name": name,
                    "active": active,
                    "deleted": None if active else NOW,
                },
            )
        assets.append(asset_id)
        blobs.append(blob_id)
        sources.append(source_id)
        return CreatedResource(
            asset_id,
            blob_id,
            source_id,
            format_resource_ref(asset_id),
            locator,
            content,
        )

    def replace_blob(created: CreatedResource, content: bytes) -> None:
        blob_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO blobs "
                    "(id,asset_id,hash,size,mime_type) "
                    "SELECT :id,asset_id,:hash,:size,mime_type "
                    "FROM blobs WHERE id=:old"
                ),
                {
                    "id": blob_id,
                    "hash": sha256(content).hexdigest(),
                    "size": len(content),
                    "old": created.blob_id,
                },
            )
            connection.execute(
                text(
                    "UPDATE asset_sources SET blob_id=:blob, "
                    "version_tag='etag-2' WHERE id=:source"
                ),
                {"blob": blob_id, "source": created.source_id},
            )
        blobs.append(blob_id)
        created.blob_id = blob_id
        created.content = content

    def add_source(
        created: CreatedResource,
        *,
        content: bytes | None = None,
    ) -> None:
        source_id = uuid4()
        blob_id = created.blob_id
        if content is not None:
            blob_id = uuid4()
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO blobs "
                        "(id,asset_id,hash,size,mime_type) "
                        "SELECT :id,asset_id,:hash,:size,mime_type "
                        "FROM blobs WHERE id=:old"
                    ),
                    {
                        "id": blob_id,
                        "hash": sha256(content).hexdigest(),
                        "size": len(content),
                        "old": created.blob_id,
                    },
                )
            blobs.append(blob_id)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO asset_sources "
                    "(id,blob_id,provider,external_id,path,name,version_tag,"
                    "metadata,is_active) SELECT "
                    ":id,:blob,provider,:locator,path,name,version_tag,"
                    "metadata,true FROM asset_sources WHERE id=:original"
                ),
                {
                    "id": source_id,
                    "blob": blob_id,
                    "locator": f"document-test-{uuid4().hex}",
                    "original": created.source_id,
                },
            )
        sources.append(source_id)

    create.replace_blob = replace_blob
    create.add_source = add_source
    try:
        yield create
    finally:
        with engine.begin() as connection:
            if assets:
                connection.execute(
                    text(
                        "DELETE FROM resource_enrichments "
                        "WHERE subject_asset_id = ANY(:ids)"
                    ),
                    {"ids": assets},
                )
                connection.execute(
                    text(
                        "DELETE FROM resource_statements "
                        "WHERE subject_asset_id = ANY(:ids)"
                    ),
                    {"ids": assets},
                )
            if sources:
                connection.execute(
                    text("DELETE FROM asset_sources WHERE id = ANY(:ids)"),
                    {"ids": sources},
                )
            if blobs:
                connection.execute(
                    text("DELETE FROM blobs WHERE id = ANY(:ids)"),
                    {"ids": blobs},
                )
            if assets:
                connection.execute(
                    text("DELETE FROM assets WHERE id = ANY(:ids)"),
                    {"ids": assets},
                )


class MutableReader:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.calls = 0

    def open(self, source):
        self.calls += 1
        yield self.content


def _owned_repository(engine, monkeypatch, resource_ref):
    repository = PostgreSQLObservationRepository(engine)
    original = repository.list_enrichment_resources

    def owned(*, provider):
        return tuple(
            resource
            for resource in original(provider=provider)
            if resource.resource_ref == resource_ref
        )

    monkeypatch.setattr(repository, "list_enrichment_resources", owned)
    return repository


@pytest.mark.parametrize("case", FORMATS, ids=lambda case: case.name)
def test_publication_idempotency_and_provenance(
    engine,
    resource_factory,
    monkeypatch,
    case,
) -> None:
    content = case.content("first excerpt")
    created = resource_factory(
        content,
        mime_type=case.mime_type,
        name=case.name,
    )
    repository = _owned_repository(
        engine,
        monkeypatch,
        created.resource_ref,
    )
    reader = MutableReader(content)
    extractor = case.extractor(reader)
    worker = EnrichmentWorker(
        repository,
        extractor,
        provider="nextcloud",
    )

    first = worker.run_once(batch_size=1)
    second = worker.run_once(batch_size=1)

    assert (first.processed, first.failed, first.statement_writes) == (
        1,
        0,
        1,
    )
    assert (second.processed, second.skipped, second.statement_writes) == (
        0,
        1,
        0,
    )
    assert reader.calls == 1
    with engine.connect() as connection:
        statement = connection.execute(
            select(
                ResourceStatementORM.string_value,
                ResourceStatementORM.generator_name,
                ResourceStatementORM.generator_version,
                ResourceStatementORM.source_kind,
                ResourceStatementORM.source_locator,
            ).where(
                ResourceStatementORM.subject_asset_id == created.asset_id,
                ResourceStatementORM.is_current.is_(True),
            )
        ).one()
    assert statement.string_value == "first excerpt"
    assert statement.generator_name == extractor.generator.generator_name
    assert statement.generator_version == "1"
    assert statement.source_kind == "resource_content"
    assert statement.source_locator == "nextcloud.webdav.content"


@pytest.mark.parametrize("case", FORMATS, ids=lambda case: case.name)
def test_zero_result_and_digest_mismatch(
    engine,
    resource_factory,
    monkeypatch,
    case,
) -> None:
    content = case.empty_content()
    created = resource_factory(
        content,
        mime_type=case.mime_type,
        name=case.name,
    )
    repository = _owned_repository(
        engine,
        monkeypatch,
        created.resource_ref,
    )
    worker = EnrichmentWorker(
        repository,
        case.extractor(MutableReader(content)),
        provider="nextcloud",
    )
    result = worker.run_once(batch_size=1)
    assert (result.processed, result.statement_writes, result.failed) == (
        1,
        0,
        0,
    )

    changed = case.content("changed after sync")
    resource_factory.replace_blob(created, case.content("stored digest"))
    mismatch = EnrichmentWorker(
        repository,
        case.extractor(MutableReader(changed)),
        provider="nextcloud",
    ).run_once(batch_size=1)
    assert mismatch.failed == 1
    state = repository.get_enrichment_state(
        created.resource_ref,
        case.extractor.generator,
    )
    assert state.error_code == "content_changed_since_sync"


@pytest.mark.parametrize("case", FORMATS, ids=lambda case: case.name)
def test_blob_update_and_same_value_history_semantics(
    engine,
    resource_factory,
    monkeypatch,
    case,
) -> None:
    first_content = case.content("first")
    created = resource_factory(
        first_content,
        mime_type=case.mime_type,
        name=case.name,
    )
    repository = _owned_repository(
        engine,
        monkeypatch,
        created.resource_ref,
    )
    reader = MutableReader(first_content)
    extractor = case.extractor(reader)
    worker = EnrichmentWorker(
        repository,
        extractor,
        provider="nextcloud",
    )
    assert worker.run_once(batch_size=1).statement_writes == 1

    second_content = case.content("second")
    resource_factory.replace_blob(created, second_content)
    reader.content = second_content
    changed = worker.run_once(batch_size=1)
    assert (changed.statement_writes, changed.deactivated_statements) == (
        1,
        1,
    )

    same_value_new_blob = second_content + b"\n"
    resource_factory.replace_blob(created, same_value_new_blob)
    reader.content = same_value_new_blob
    same = worker.run_once(batch_size=1)
    assert (same.statement_writes, same.deactivated_statements) == (0, 0)
    with engine.connect() as connection:
        rows = connection.execute(
            select(ResourceStatementORM).where(
                ResourceStatementORM.subject_asset_id == created.asset_id
            )
        ).scalars().all()
    assert len(rows) == 2


@pytest.mark.parametrize("case", FORMATS, ids=lambda case: case.name)
def test_inactive_same_blob_and_distinct_blob_source_semantics(
    engine,
    resource_factory,
    monkeypatch,
    case,
) -> None:
    content = case.content("source semantics")
    inactive = resource_factory(
        content,
        mime_type=case.mime_type,
        name=case.name,
        active=False,
    )
    repository = PostgreSQLObservationRepository(engine)
    assert inactive.resource_ref not in {
        resource.resource_ref
        for resource in repository.list_enrichment_resources(
            provider="nextcloud"
        )
    }

    same = resource_factory(
        content,
        mime_type=case.mime_type,
        name=case.name,
    )
    resource_factory.add_source(same)
    owned = _owned_repository(engine, monkeypatch, same.resource_ref)
    result = EnrichmentWorker(
        owned,
        case.extractor(MutableReader(content)),
        provider="nextcloud",
    ).run_once(batch_size=1)
    assert (result.processed, result.failed) == (1, 0)

    distinct = resource_factory(
        content,
        mime_type=case.mime_type,
        name=case.name,
    )
    resource_factory.add_source(
        distinct,
        content=case.content("different source"),
    )
    distinct_repository = _owned_repository(
        engine,
        monkeypatch,
        distinct.resource_ref,
    )
    ambiguous = EnrichmentWorker(
        distinct_repository,
        case.extractor(MutableReader(content)),
        provider="nextcloud",
    ).run_once(batch_size=1)
    assert ambiguous.failed == 1
    assert ambiguous.processed == 0


def _existing_excerpt(resource_ref, generator_name, value="old"):
    return ObservationBatch(
        resource_ref,
        GeneratorIdentity(
            "deterministic_extractor",
            generator_name,
            "1",
        ),
        ("document.text_excerpt",),
        "a" * 64,
        (
            StatementDraft(
                "document.text_excerpt",
                TypedStatementValue(StatementValueType.STRING, value),
                Evidence(
                    EvidenceSourceKind.RESOURCE_CONTENT,
                    "nextcloud.webdav.content",
                ),
            ),
        ),
    )


@pytest.mark.parametrize(
    ("existing_generator", "case"),
    (
        ("nextcloud_text", FORMATS[0]),
        ("nextcloud_pdf", FORMATS[2]),
    ),
)
def test_multi_generator_lifecycle_guard_preserves_existing_current(
    engine,
    resource_factory,
    monkeypatch,
    existing_generator,
    case,
) -> None:
    content = case.content("new")
    created = resource_factory(
        content,
        mime_type=case.mime_type,
        name=case.name,
    )
    repository = _owned_repository(
        engine,
        monkeypatch,
        created.resource_ref,
    )
    repository.publish(
        _existing_excerpt(created.resource_ref, existing_generator),
        completed_at=NOW,
    )

    result = EnrichmentWorker(
        repository,
        case.extractor(MutableReader(content)),
        provider="nextcloud",
    ).run_once(batch_size=1)

    assert result.failed == 1
    assert result.statement_writes == 0
    state = repository.get_enrichment_state(
        created.resource_ref,
        case.extractor.generator,
    )
    assert state.error_code == "ambiguous_document_generator_state"
    with engine.connect() as connection:
        current = connection.execute(
            select(
                ResourceStatementORM.generator_name,
                ResourceStatementORM.string_value,
                ResourceStatementORM.is_current,
            ).where(
                ResourceStatementORM.subject_asset_id == created.asset_id
            )
        ).all()
    assert current == [(existing_generator, "old", True)]


def test_mcp_serializes_real_rich_document_without_leakage(
    engine,
    resource_factory,
    monkeypatch,
) -> None:
    content = _odt("<text:p>MCP excerpt</text:p>")
    created = resource_factory(
        content,
        mime_type=ODT_MIME,
        name="mcp.odt",
    )
    repository = _owned_repository(
        engine,
        monkeypatch,
        created.resource_ref,
    )
    result = EnrichmentWorker(
        repository,
        NextcloudODTExtractor(MutableReader(content)),
        provider="nextcloud",
    ).run_once(batch_size=1)
    assert result.statement_writes == 1

    async def exercise() -> None:
        async with Client(
            create_runtime_server(require_safe_test_database_url())
        ) as client:
            tools = (await client.list_tools()).tools
            response = await client.call_tool(
                "pdi_get_resource_observations",
                {
                    "resource_ref": created.resource_ref,
                    "predicate": "document.text_excerpt",
                },
            )
        assert len(tools) == 9
        observation = response.structured_content["observations"][0]
        assert observation["value"] == "MCP excerpt"
        assert observation["generator_name"] == "nextcloud_odt"
        assert observation["source_locator"] == (
            "nextcloud.webdav.content"
        )
        payload = str(response.structured_content)
        for private in (
            created.locator,
            str(created.asset_id),
            str(created.blob_id),
            str(created.source_id),
            "provider_locator",
            "href",
            "/tmp/",
        ):
            if private == str(created.asset_id):
                payload = payload.replace(created.resource_ref, "")
            assert private not in payload

    asyncio.run(exercise())


def test_guard_family_is_exactly_frozen() -> None:
    assert DOCUMENT_GENERATOR_FAMILY == (
        "nextcloud_text",
        "nextcloud_pdf",
        "nextcloud_odt",
        "nextcloud_docx",
    )
