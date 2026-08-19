from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
import pytest
import requests
from sqlalchemy import Engine, create_engine, select, text

from pdi.observation import (
    EnrichmentWorker,
    MAX_STORED_TEXT_BYTES,
    NextcloudContentReader,
    NextcloudTextExtractor,
    PostgreSQLObservationRepository,
)
from pdi.query import format_resource_ref
from pdi.repository.orm.observation import (
    ResourceEnrichmentORM,
    ResourceStatementORM,
)
from tests.integration.database_guard import require_safe_test_database_url


ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)


@dataclass
class CreatedResource:
    asset_id: UUID
    source_id: UUID
    blob_id: UUID
    resource_ref: str
    href: str
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
    asset_ids: list[UUID] = []
    source_ids: list[UUID] = []
    blob_ids: list[UUID] = []

    def create(
        content: bytes,
        *,
        active: bool = True,
        mime_type: str = "text/markdown",
        name: str = "notes.md",
    ) -> CreatedResource:
        asset_id = uuid4()
        blob_id = uuid4()
        source_id = uuid4()
        token = uuid4().hex
        href = f"/test-only/{token}"
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO assets "
                    "(id,resource_type,title,metadata,created_at,updated_at) "
                    "VALUES (:id,'file',:title,'{}'::jsonb,:now,:now)"
                ),
                {
                    "id": asset_id,
                    "title": f"nextcloud-text-{token}",
                    "now": NOW,
                },
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
                    "(id,blob_id,provider,external_id,path,name,"
                    "version_tag,metadata,is_active,deleted_at) "
                    "VALUES (:id,:blob,'nextcloud',:external,:path,"
                    ":name,'etag-1',CAST(:metadata AS jsonb),:active,"
                    ":deleted_at)"
                ),
                {
                    "id": source_id,
                    "blob": blob_id,
                    "external": f"nextcloud-text-{token}",
                    "path": f"test-only/{name}",
                    "name": name,
                    "metadata": '{"href":"' + href + '"}',
                    "active": active,
                    "deleted_at": None if active else NOW,
                },
            )
        asset_ids.append(asset_id)
        blob_ids.append(blob_id)
        source_ids.append(source_id)
        return CreatedResource(
            asset_id,
            source_id,
            blob_id,
            format_resource_ref(asset_id),
            href,
            content,
        )

    def replace_blob(
        created: CreatedResource,
        content: bytes,
        *,
        mime_type: str = "text/markdown",
    ) -> UUID:
        blob_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO blobs "
                    "(id,asset_id,hash,size,mime_type) "
                    "VALUES (:id,:asset,:hash,:size,:mime)"
                ),
                {
                    "id": blob_id,
                    "asset": created.asset_id,
                    "hash": sha256(content).hexdigest(),
                    "size": len(content),
                    "mime": mime_type,
                },
            )
            connection.execute(
                text(
                    "UPDATE asset_sources SET blob_id=:blob, "
                    "version_tag='etag-2' WHERE id=:source"
                ),
                {"blob": blob_id, "source": created.source_id},
            )
        blob_ids.append(blob_id)
        created.blob_id = blob_id
        created.content = content
        return blob_id

    create.replace_blob = replace_blob
    try:
        yield create
    finally:
        with engine.begin() as connection:
            if asset_ids:
                connection.execute(
                    ResourceEnrichmentORM.__table__.delete().where(
                        ResourceEnrichmentORM.subject_asset_id.in_(asset_ids)
                    )
                )
                connection.execute(
                    ResourceStatementORM.__table__.delete().where(
                        ResourceStatementORM.subject_asset_id.in_(asset_ids)
                    )
                )
            if source_ids:
                connection.execute(
                    text("DELETE FROM asset_sources WHERE id = ANY(:ids)"),
                    {"ids": source_ids},
                )
            if blob_ids:
                connection.execute(
                    text("DELETE FROM blobs WHERE id = ANY(:ids)"),
                    {"ids": blob_ids},
                )
            if asset_ids:
                connection.execute(
                    text("DELETE FROM assets WHERE id = ANY(:ids)"),
                    {"ids": asset_ids},
                )


class MutableAdapter:
    def __init__(self, contents: dict[str, bytes]) -> None:
        self.contents = contents
        self.calls = 0
        self.error: Exception | None = None

    def open(self, fact):
        self.calls += 1
        if self.error is not None:
            raise self.error
        yield self.contents[fact.raw["href"]]


def _owned_repository(engine, monkeypatch, resource_ref):
    repository = PostgreSQLObservationRepository(engine)
    original = repository.list_enrichment_resources

    def list_owned(*, provider):
        return tuple(
            resource
            for resource in original(provider=provider)
            if resource.resource_ref == resource_ref
        )

    monkeypatch.setattr(
        repository,
        "list_enrichment_resources",
        list_owned,
    )
    return repository


def test_projection_reader_statement_and_second_run_zero_io(
    engine,
    resource_factory,
    monkeypatch,
) -> None:
    created = resource_factory(b"# Project\n\nArchitecture first.\n")
    repository = _owned_repository(
        engine,
        monkeypatch,
        created.resource_ref,
    )
    projected = repository.list_enrichment_resources(
        provider="nextcloud"
    )[0]
    source = projected.sources[0]
    assert source.blob_sha256 == sha256(created.content).hexdigest()
    assert source.size == len(created.content)
    assert source.mime_type == "text/markdown"
    assert source.name == "notes.md"
    assert source.path == "test-only/notes.md"
    assert source.version_tag == "etag-1"

    adapter = MutableAdapter({created.href: created.content})
    worker = EnrichmentWorker(
        repository,
        NextcloudTextExtractor(NextcloudContentReader(adapter)),
        provider="nextcloud",
    )
    first = worker.run_once(batch_size=1)
    assert (first.processed, first.failed, first.statement_writes) == (
        1,
        0,
        1,
    )
    assert adapter.calls == 1

    with engine.connect() as connection:
        statement = connection.execute(
            select(
                ResourceStatementORM.predicate,
                ResourceStatementORM.string_value,
                ResourceStatementORM.generator_type,
                ResourceStatementORM.generator_name,
                ResourceStatementORM.generator_version,
                ResourceStatementORM.source_kind,
                ResourceStatementORM.source_locator,
                ResourceStatementORM.confidence,
            ).where(
                ResourceStatementORM.subject_asset_id == created.asset_id,
                ResourceStatementORM.is_current.is_(True),
            )
        ).one()
    assert statement.predicate == "document.text_excerpt"
    assert statement.string_value == created.content.decode()
    assert statement.generator_type == "deterministic_extractor"
    assert statement.generator_name == "nextcloud_text"
    assert statement.generator_version == "1"
    assert statement.source_kind == "resource_content"
    assert statement.source_locator == "nextcloud.webdav.content"
    assert statement.confidence is None

    second = worker.run_once(batch_size=1)
    assert (second.processed, second.skipped, second.statement_writes) == (
        0,
        1,
        0,
    )
    assert adapter.calls == 1


def test_blob_change_replaces_changed_excerpt(
    engine,
    resource_factory,
    monkeypatch,
) -> None:
    first_content = b"first excerpt"
    second_content = b"second excerpt"
    created = resource_factory(first_content)
    repository = _owned_repository(
        engine,
        monkeypatch,
        created.resource_ref,
    )
    adapter = MutableAdapter({created.href: first_content})
    worker = EnrichmentWorker(
        repository,
        NextcloudTextExtractor(NextcloudContentReader(adapter)),
        provider="nextcloud",
    )
    assert worker.run_once(batch_size=1).statement_writes == 1

    resource_factory.replace_blob(created, second_content)
    adapter.contents[created.href] = second_content
    changed = worker.run_once(batch_size=1)
    assert (changed.statement_writes, changed.deactivated_statements) == (
        1,
        1,
    )

    with engine.connect() as connection:
        history = connection.execute(
            select(
                ResourceStatementORM.string_value,
                ResourceStatementORM.is_current,
            )
            .where(
                ResourceStatementORM.subject_asset_id == created.asset_id
            )
            .order_by(ResourceStatementORM.created_at.asc())
        ).all()
    assert history == [
        ("first excerpt", False),
        ("second excerpt", True),
    ]


def test_suffix_only_change_updates_fingerprint_without_statement_churn(
    engine,
    resource_factory,
    monkeypatch,
) -> None:
    shared_prefix = b"a" * MAX_STORED_TEXT_BYTES
    first_content = shared_prefix + b"first suffix"
    second_content = shared_prefix + b"second different suffix"
    created = resource_factory(first_content)
    repository = _owned_repository(
        engine,
        monkeypatch,
        created.resource_ref,
    )
    adapter = MutableAdapter({created.href: first_content})
    worker = EnrichmentWorker(
        repository,
        NextcloudTextExtractor(NextcloudContentReader(adapter)),
        provider="nextcloud",
    )
    assert worker.run_once(batch_size=1).statement_writes == 1
    first_state = repository.get_enrichment_state(
        created.resource_ref,
        NextcloudTextExtractor.generator,
    )

    resource_factory.replace_blob(created, second_content)
    adapter.contents[created.href] = second_content
    changed = worker.run_once(batch_size=1)
    second_state = repository.get_enrichment_state(
        created.resource_ref,
        NextcloudTextExtractor.generator,
    )

    assert changed.processed == 1
    assert changed.statement_writes == 0
    assert changed.deactivated_statements == 0
    assert first_state.input_fingerprint != second_state.input_fingerprint
    with engine.connect() as connection:
        statement_count = connection.execute(
            select(ResourceStatementORM).where(
                ResourceStatementORM.subject_asset_id == created.asset_id
            )
        ).scalars().all()
    assert len(statement_count) == 1


def test_inactive_source_is_not_discovered(
    engine,
    resource_factory,
) -> None:
    created = resource_factory(b"inactive", active=False)
    repository = PostgreSQLObservationRepository(engine)
    refs = {
        resource.resource_ref
        for resource in repository.list_enrichment_resources(
            provider="nextcloud"
        )
    }

    assert created.resource_ref not in refs


@pytest.mark.parametrize(
    ("mode", "expected_code"),
    [
        ("provider", "provider_read_failed"),
        ("decode", "invalid_text_encoding"),
        ("digest", "content_changed_since_sync"),
    ],
)
def test_failures_record_sanitized_state_without_statements(
    engine,
    resource_factory,
    monkeypatch,
    mode,
    expected_code,
) -> None:
    stored_content = b"valid"
    created = resource_factory(stored_content)
    repository = _owned_repository(
        engine,
        monkeypatch,
        created.resource_ref,
    )
    adapter = MutableAdapter({created.href: stored_content})
    if mode == "provider":
        adapter.error = requests.HTTPError(
            "https://secret.invalid/private?password=secret"
        )
    elif mode == "decode":
        invalid = b"\xff"
        resource_factory.replace_blob(created, invalid)
        adapter.contents[created.href] = invalid
    else:
        adapter.contents[created.href] = b"changed after sync"

    result = EnrichmentWorker(
        repository,
        NextcloudTextExtractor(NextcloudContentReader(adapter)),
        provider="nextcloud",
    ).run_once(batch_size=1)

    assert result.failed == 1
    state = repository.get_enrichment_state(
        created.resource_ref,
        NextcloudTextExtractor.generator,
    )
    assert state.status == "failed"
    assert state.error_code == expected_code
    assert "secret" not in state.error_message
    assert "http" not in state.error_message.lower()
    with engine.connect() as connection:
        count = connection.execute(
            select(ResourceStatementORM).where(
                ResourceStatementORM.subject_asset_id == created.asset_id
            )
        ).scalars().all()
    assert count == []
