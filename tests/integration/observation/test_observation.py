from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.exc import IntegrityError

from pdi.observation import (
    EnrichmentResource,
    EnrichmentSource,
    EnrichmentWorker,
    Evidence,
    EvidenceSourceKind,
    GeneratorIdentity,
    ImmichMetadataExtractor,
    ObservationBatch,
    ObservationService,
    ObservationResourceNotFoundError,
    PostgreSQLObservationRepository,
    StatementDraft,
    StatementValueType,
    TypedStatementValue,
)
from pdi.query import format_resource_ref
from pdi.repository.orm.observation import ResourceEnrichmentORM, ResourceStatementORM
from tests.integration.database_guard import require_safe_test_database_url


ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 8, 13, 12, tzinfo=UTC)


def _upgrade(engine: Engine) -> None:
    with engine.connect() as connection:
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@pytest.fixture(scope="module")
def context():
    engine = create_engine(require_safe_test_database_url())
    _upgrade(engine)
    token = uuid4().hex
    ids = [uuid4(), uuid4()]
    with engine.begin() as connection:
        for index, asset_id in enumerate(ids):
            blob_id, source_id = uuid4(), uuid4()
            connection.execute(text(
                "INSERT INTO assets (id,resource_type,title,metadata,created_at,updated_at) "
                "VALUES (:id,'file',:title,'{}'::jsonb,:now,:now)"
            ), {"id": asset_id, "title": f"observation-{token}-{index}", "now": NOW})
            connection.execute(text(
                "INSERT INTO blobs (id,asset_id,hash,size,mime_type) "
                "VALUES (:id,:asset,:hash,1,'image/jpeg')"
            ), {"id": blob_id, "asset": asset_id, "hash": f"observation-{token}-{index}"})
            connection.execute(text(
                "INSERT INTO asset_sources (id,blob_id,provider,external_id,path,name,version_tag,metadata,is_active) "
                "VALUES (:id,:blob,'immich',:external,NULL,'photo.jpg','1',CAST(:metadata AS jsonb),true)"
            ), {"id": source_id, "blob": blob_id, "external": f"observation-{token}-{index}", "metadata": '{"exif":{"dateTimeOriginal":"2020-01-02T03:04:05+08:00","latitude":31.2,"longitude":121.5,"make":"Apple","model":"iPhone"}}'})
    repository = PostgreSQLObservationRepository(engine)
    try:
        yield engine, repository, ids
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM resource_enrichments WHERE subject_asset_id = ANY(:ids)"), {"ids": ids})
            connection.execute(text("DELETE FROM resource_statements WHERE subject_asset_id = ANY(:ids) OR resource_value_asset_id = ANY(:ids)"), {"ids": ids})
            connection.execute(text("DELETE FROM asset_sources WHERE external_id LIKE :prefix"), {"prefix": f"observation-{token}-%"})
            connection.execute(text("DELETE FROM blobs WHERE hash LIKE :prefix"), {"prefix": f"observation-{token}-%"})
            connection.execute(text("DELETE FROM assets WHERE id = ANY(:ids)"), {"ids": ids})
        engine.dispose()


def _batch(asset_id, value="A", *, generator=None, fingerprint="a" * 64, predicate="media.camera_make"):
    generator = generator or GeneratorIdentity("deterministic_extractor", "test", "1")
    statements = () if value is None else (StatementDraft(
        predicate,
        TypedStatementValue(StatementValueType.STRING, value),
        Evidence(EvidenceSourceKind.PROVIDER_METADATA, "asset_source.metadata.exif.make"),
    ),)
    return ObservationBatch(format_resource_ref(asset_id), generator, (predicate,), fingerprint, statements)


def test_statement_constraints_are_enforced_by_postgresql(context) -> None:
    engine, _, ids = context
    base = {
        "id": uuid4(), "subject": ids[0], "predicate": "media.camera_make",
        "value_type": "string", "string_value": "Apple", "integer_value": None,
        "generator_type": "deterministic_extractor", "generator_name": "constraint",
        "generator_version": "1", "source_kind": "provider_metadata",
        "source_locator": "asset_source.metadata.exif.make", "confidence": None,
    }
    sql = text("INSERT INTO resource_statements "
        "(id,subject_asset_id,predicate,value_type,string_value,integer_value,generator_type,generator_name,generator_version,source_kind,source_locator,confidence) "
        "VALUES (:id,:subject,:predicate,:value_type,:string_value,:integer_value,:generator_type,:generator_name,:generator_version,:source_kind,:source_locator,:confidence)")
    invalids = (
        {"string_value": None},
        {"integer_value": 1},
        {"value_type": "integer"},
        {"confidence": float("nan")},
        {"confidence": 1.1},
        {"predicate": ""},
        {"generator_name": ""},
        {"source_kind": "unknown"},
        {"source_locator": ""},
        {"subject": uuid4()},
    )
    for changes in invalids:
        values = {**base, "id": uuid4(), **changes}
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(sql, values)
    resource_values = {**base, "id": uuid4(), "value_type": "resource_ref", "string_value": None, "subject": ids[0]}
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text(str(sql).replace("integer_value,generator_type", "integer_value,resource_value_asset_id,generator_type").replace(":integer_value,:generator_type", ":integer_value,:resource_value_asset_id,:generator_type")), {**resource_values, "resource_value_asset_id": uuid4()})


def test_publish_idempotency_history_zero_and_generator_isolation(context) -> None:
    engine, repository, ids = context
    service = ObservationService(repository)
    asset_id = ids[0]
    assert service.publish(_batch(asset_id, "A"), completed_at=NOW).statement_writes == 1
    assert service.publish(_batch(asset_id, "A"), completed_at=NOW + timedelta(seconds=1)).statement_writes == 0
    changed = service.publish(_batch(asset_id, "B", fingerprint="b" * 64), completed_at=NOW + timedelta(seconds=2))
    assert (changed.statement_writes, changed.deactivated_statements) == (1, 1)
    assert service.publish(_batch(asset_id, "A", fingerprint="c" * 64), completed_at=NOW + timedelta(seconds=3)).statement_writes == 1
    assert service.publish(_batch(asset_id, None, fingerprint="d" * 64), completed_at=NOW + timedelta(seconds=4)).deactivated_statements == 1
    second = GeneratorIdentity("deterministic_extractor", "other", "1")
    third = GeneratorIdentity("other_type", "test", "2")
    service.publish(_batch(asset_id, "X", generator=second, fingerprint="e" * 64), completed_at=NOW)
    service.publish(_batch(asset_id, "Y", generator=third, fingerprint="f" * 64), completed_at=NOW)
    with engine.connect() as connection:
        history = connection.execute(text("SELECT string_value,is_current FROM resource_statements WHERE subject_asset_id=:id AND generator_name='test' AND generator_type='deterministic_extractor' ORDER BY created_at"), {"id": asset_id}).all()
        current_count = connection.execute(text("SELECT count(*) FROM resource_statements WHERE subject_asset_id=:id AND is_current"), {"id": asset_id}).scalar_one()
    assert history == [("A", False), ("B", False), ("A", False)]
    assert current_count == 2


def test_ocr_statement_lifecycle_and_internal_locator_discovery(context) -> None:
    engine, repository, ids = context
    asset_id = ids[1]
    resource_ref = format_resource_ref(asset_id)
    generator = GeneratorIdentity(
        "provider_native_ml",
        "immich_ocr",
        "1",
    )

    discovered = {
        resource.resource_ref: resource
        for resource in repository.list_enrichment_resources(
            provider="immich"
        )
    }
    source = discovered[resource_ref].sources[0]
    assert source.provider_locator is not None
    assert source.provider_locator.startswith("observation-")

    initial = _batch(
        asset_id,
        "first OCR text",
        generator=generator,
        fingerprint="1" * 64,
        predicate="media.ocr_text",
    )
    assert repository.publish(initial, completed_at=NOW).statement_writes == 1
    unchanged = repository.publish(
        initial,
        completed_at=NOW + timedelta(seconds=1),
    )
    assert (unchanged.statement_writes, unchanged.deactivated_statements) == (
        0,
        0,
    )

    changed = _batch(
        asset_id,
        "second OCR text",
        generator=generator,
        fingerprint="2" * 64,
        predicate="media.ocr_text",
    )
    result = repository.publish(
        changed,
        completed_at=NOW + timedelta(seconds=2),
    )
    assert (result.statement_writes, result.deactivated_statements) == (1, 1)

    zero = _batch(
        asset_id,
        None,
        generator=generator,
        fingerprint="3" * 64,
        predicate="media.ocr_text",
    )
    result = repository.publish(
        zero,
        completed_at=NOW + timedelta(seconds=3),
    )
    assert (result.statement_writes, result.deactivated_statements) == (0, 1)
    assert repository.get_enrichment_state(
        resource_ref,
        generator,
    ).status == "completed"

    isolated = GeneratorIdentity(
        "provider_native_ml",
        "other_ocr",
        "1",
    )
    repository.publish(
        _batch(
            asset_id,
            "isolated",
            generator=isolated,
            fingerprint="4" * 64,
            predicate="media.ocr_text",
        ),
        completed_at=NOW + timedelta(seconds=4),
    )
    with engine.connect() as connection:
        history = connection.execute(
            text(
                "SELECT string_value,is_current FROM resource_statements "
                "WHERE subject_asset_id=:id "
                "AND generator_type='provider_native_ml' "
                "AND generator_name='immich_ocr' "
                "ORDER BY created_at"
            ),
            {"id": asset_id},
        ).all()
        isolated_current = connection.execute(
            text(
                "SELECT count(*) FROM resource_statements "
                "WHERE subject_asset_id=:id "
                "AND generator_name='other_ocr' AND is_current"
            ),
            {"id": asset_id},
        ).scalar_one()
    assert history == [
        ("first OCR text", False),
        ("second OCR text", False),
    ]
    assert isolated_current == 1


def test_state_discovery_zero_result_stale_retry_and_safe_errors(context) -> None:
    engine, repository, ids = context
    resource_ref = format_resource_ref(ids[1])
    generator = GeneratorIdentity("deterministic_extractor", "state-test", "1")
    assert repository.get_enrichment_state(resource_ref, generator) is None
    assert repository.mark_running(resource_ref, generator, "1" * 64, now=NOW, stale_after=timedelta(minutes=30))
    assert repository.get_enrichment_state(resource_ref, generator).status == "running"
    assert not repository.mark_running(resource_ref, generator, "1" * 64, now=NOW + timedelta(minutes=1), stale_after=timedelta(minutes=30))
    assert repository.mark_running(resource_ref, generator, "1" * 64, now=NOW + timedelta(minutes=31), stale_after=timedelta(minutes=30))
    empty = ObservationBatch(resource_ref, generator, ("media.latitude", "media.longitude"), "1" * 64, ())
    repository.publish(empty, completed_at=NOW + timedelta(minutes=32))
    state = repository.get_enrichment_state(resource_ref, generator)
    assert state.status == "completed" and state.completed_at is not None
    assert not repository.mark_running(resource_ref, generator, "1" * 64, now=NOW + timedelta(hours=1), stale_after=timedelta(minutes=30))
    assert repository.mark_running(resource_ref, generator, "2" * 64, now=NOW + timedelta(hours=1), stale_after=timedelta(minutes=30))
    repository.mark_failed(resource_ref, generator, "2" * 64, now=NOW + timedelta(hours=1), error_code="safe_error", error_message="x" * 1000)
    state = repository.get_enrichment_state(resource_ref, generator)
    assert state.status == "failed" and state.error_code == "safe_error" and len(state.error_message) == 512


def test_worker_is_bounded_and_second_run_skips_unchanged(
    context,
    monkeypatch,
) -> None:
    _, repository, ids = context
    owned_refs = {format_resource_ref(asset_id) for asset_id in ids}
    resources = repository.list_enrichment_resources(provider="immich")
    monkeypatch.setattr(
        repository,
        "list_enrichment_resources",
        lambda *, provider: tuple(
            resource
            for resource in resources
            if resource.resource_ref in owned_refs
        ),
    )
    extractor = ImmichMetadataExtractor()
    worker = EnrichmentWorker(repository, extractor, clock=lambda: NOW + timedelta(days=1))
    first = worker.run_once(batch_size=1)
    assert first.processed == 1 and first.failed == 0 and first.statement_writes == 5
    second = worker.run_once(batch_size=10)
    assert second.failed == 0
    assert second.statement_writes <= 5
    third = worker.run_once(batch_size=10)
    assert third.statement_writes == 0 and third.processed == 0 and third.skipped >= 2


def test_failed_publish_rolls_back_state_and_statements(context) -> None:
    engine, repository, ids = context
    missing_target = format_resource_ref(uuid4())
    bad = ObservationBatch(
        format_resource_ref(ids[1]), GeneratorIdentity("deterministic_extractor", "rollback", "1"),
        ("media.camera_make",), "9" * 64,
        (StatementDraft("media.camera_make", TypedStatementValue(StatementValueType.STRING, "A"), Evidence(EvidenceSourceKind.PROVIDER_METADATA, "safe")),),
    )
    # Force a DB failure after state creation by replacing the typed value with
    # an unresolved resource FK at the persistence boundary.
    object.__setattr__(bad.statements[0], "value", TypedStatementValue(StatementValueType.RESOURCE_REF, missing_target))
    with pytest.raises(IntegrityError):
        repository.publish(bad, completed_at=NOW)
    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(ResourceEnrichmentORM).where(ResourceEnrichmentORM.extractor_name == "rollback")).scalar_one() == 0
        assert connection.execute(select(func.count()).select_from(ResourceStatementORM).where(ResourceStatementORM.generator_name == "rollback")).scalar_one() == 0


def test_query_current_history_filter_order_empty_and_not_found(context) -> None:
    engine, repository, ids = context
    service = ObservationService(repository)
    resource_ref = format_resource_ref(ids[0])

    current = service.get_resource_statements(resource_ref)
    assert tuple(
        (
            item.predicate,
            item.generator.generator_type,
            item.generator.generator_name,
            item.generator.generator_version,
        )
        for item in current
    ) == tuple(sorted(
        (
            item.predicate,
            item.generator.generator_type,
            item.generator.generator_name,
            item.generator.generator_version,
        )
        for item in current
    ))
    assert all(item.is_current for item in current)
    filtered = service.get_resource_statements(
        resource_ref,
        predicate="media.camera_make",
    )
    assert all(item.predicate == "media.camera_make" for item in filtered)
    history = service.get_resource_statements(
        resource_ref,
        predicate="media.camera_make",
        include_history=True,
    )
    assert len(history) >= len(filtered)
    assert any(not item.is_current for item in history)
    empty_asset_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO assets "
                "(id,resource_type,title,metadata,created_at,updated_at) "
                "VALUES (:id,'file','observation-empty','{}'::jsonb,:now,:now)"
            ),
            {"id": empty_asset_id, "now": NOW},
        )
    try:
        assert service.get_resource_statements(
            format_resource_ref(empty_asset_id)
        ) == ()
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM assets WHERE id=:id"),
                {"id": empty_asset_id},
            )
    # Views remain fully usable after the repository Session has closed.
    assert all(item.generator.generator_name for item in history)
    with pytest.raises(ObservationResourceNotFoundError):
        service.get_resource_statements(format_resource_ref(uuid4()))
