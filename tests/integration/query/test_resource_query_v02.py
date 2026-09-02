import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from mcp import Client
import pytest
from sqlalchemy import Connection, Engine, delete
from sqlalchemy.orm import Session

from pdi.database import create_postgres_engine
from pdi.decision import Action, ActionType, Decision
from pdi.models import Asset, AssetSource, Blob
from pdi.query import (
    QueryService,
    ResourceGroupBy,
    format_resource_ref,
    parse_resource_ref,
)
from pdi.repository import PostgreSQLRepository
from pdi.repository.orm.observation import ResourceStatementORM
from pdi.repository.orm.person import PersonORM, PersonSourceORM
from pdi_mcp.bootstrap import create_runtime_server
from tests.integration.database_guard import require_safe_test_database_url


ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class V02Data:
    now: datetime
    observed_from: datetime
    observed_to: datetime
    provider: str
    alternate_provider: str
    path_prefix: str
    expected_recent_refs: tuple[str, ...]
    tied_refs: tuple[str, ...]
    multi_provider_ref: str


def _alembic_config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def _upgrade_schema(engine: Engine) -> None:
    with engine.connect() as connection:
        command.upgrade(_alembic_config(connection), "head")


def _source_actions(
    *,
    asset: Asset,
    provider: str,
    path: str,
    mime_type: str | None,
    active: bool = True,
) -> tuple[list[Action], AssetSource]:
    blob = Blob(
        asset_id=asset.id,
        hash=f"query-v02-{uuid4()}",
        size=100,
        mime_type=mime_type,
    )
    source = AssetSource(
        blob_id=blob.id,
        provider=provider,
        external_id=f"query-v02-source-{uuid4()}",
        path=path,
        name=path.rsplit("/", 1)[-1],
        is_active=active,
        deleted_at=None if active else datetime.now(UTC),
    )
    return [
        Action(type=ActionType.CREATE_BLOB, blob=blob),
        Action(type=ActionType.CREATE_SOURCE, source=source),
    ], source


def _create_data(repository: PostgreSQLRepository) -> V02Data:
    token = uuid4().hex
    now = datetime(2026, 8, 12, 12, tzinfo=UTC)
    observed_from = now - timedelta(days=3)
    provider = f"query-v02-primary-{token}"
    alternate_provider = f"query-v02-alternate-{token}"
    path_prefix = f"/query-v02/{token}"
    tied_ids = sorted((uuid4(), uuid4()))

    boundary = Asset(
        title=f"Boundary {token}",
        created_at=observed_from,
        updated_at=observed_from,
    )
    tied_first = Asset(
        id=str(tied_ids[0]),
        title=f"SearchTie {token}",
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
    )
    tied_second = Asset(
        id=str(tied_ids[1]),
        title=f"SearchTie {token}",
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
    )
    multi_provider = Asset(
        title=f"Multi Provider {token}",
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
    )
    malformed = Asset(
        title=f"Malformed MIME {token}",
        created_at=now - timedelta(hours=12),
        updated_at=now - timedelta(hours=12),
    )
    unknown = Asset(
        title=f"Unknown MIME {token}",
        created_at=now - timedelta(hours=13),
        updated_at=now - timedelta(hours=13),
    )
    inactive = Asset(
        title=f"Inactive {token}",
        created_at=now - timedelta(hours=10),
        updated_at=now - timedelta(hours=10),
    )
    zero_source = Asset(
        title=f"Zero Source {token}",
        created_at=now - timedelta(hours=9),
        updated_at=now - timedelta(hours=9),
    )
    exclusive_boundary = Asset(
        title=f"Exclusive Boundary {token}",
        created_at=now,
        updated_at=now,
    )

    assets = (
        boundary,
        tied_first,
        tied_second,
        multi_provider,
        malformed,
        unknown,
        inactive,
        zero_source,
        exclusive_boundary,
    )
    actions = [
        Action(type=ActionType.CREATE_ASSET, asset=asset)
        for asset in assets
    ]

    source_specs = (
        (boundary, provider, "boundary.jpg", "image/jpeg", True),
        (tied_first, provider, "search-tie-a.md", "text/markdown", True),
        (tied_second, provider, "search-tie-b.md", "text/markdown", True),
        (multi_provider, provider, "multi-note.md", "text/markdown", True),
        (multi_provider, provider, "multi-image.png", "image/png", True),
        (
            multi_provider,
            alternate_provider,
            "multi-photo.jpg",
            "image/jpeg",
            True,
        ),
        (malformed, provider, "malformed.bin", "malformed", True),
        (unknown, provider, "unknown.bin", None, True),
        (inactive, provider, "inactive.jpg", "image/jpeg", False),
        (
            exclusive_boundary,
            provider,
            "exclusive.mp4",
            "video/mp4",
            True,
        ),
    )
    for asset, source_provider, name, mime_type, active in source_specs:
        source_actions, _ = _source_actions(
            asset=asset,
            provider=source_provider,
            path=f"{path_prefix}/{name}",
            mime_type=mime_type,
            active=active,
        )
        actions.extend(source_actions)

    repository.execute(Decision(actions=actions))

    expected_order = (
        malformed,
        unknown,
        multi_provider,
        tied_first,
        tied_second,
        boundary,
    )
    return V02Data(
        now=now,
        observed_from=observed_from,
        observed_to=now,
        provider=provider,
        alternate_provider=alternate_provider,
        path_prefix=path_prefix,
        expected_recent_refs=tuple(
            format_resource_ref(asset.id) for asset in expected_order
        ),
        tied_refs=(
            format_resource_ref(tied_first.id),
            format_resource_ref(tied_second.id),
        ),
        multi_provider_ref=format_resource_ref(multi_provider.id),
    )


@pytest.fixture(scope="module")
def v02_context():
    database_url = require_safe_test_database_url()
    engine = create_postgres_engine(database_url)
    _upgrade_schema(engine)
    repository = PostgreSQLRepository(engine)
    data = _create_data(repository)
    service = QueryService(repository, clock=lambda: data.now)
    try:
        yield database_url, repository, service, data
    finally:
        engine.dispose()


def test_aggregation_boundaries_days_and_mime_semantics(v02_context) -> None:
    _, _, service, data = v02_context

    count = service.aggregate_resources(
        observed_from=data.observed_from,
        observed_to=data.observed_to,
        path_prefix=data.path_prefix,
    )
    assert count.total_count == 6
    assert count.buckets == ()

    day = service.aggregate_resources(
        group_by="day",
        observed_from=data.observed_from,
        observed_to=data.observed_to,
        path_prefix=data.path_prefix,
    )
    assert [(bucket.key, bucket.count) for bucket in day.buckets] == [
        ("2026-08-09", 1),
        ("2026-08-10", 2),
        ("2026-08-11", 2),
        ("2026-08-12", 1),
    ]

    categories = service.aggregate_resources(
        group_by="mime_category",
        observed_from=data.observed_from,
        observed_to=data.observed_to,
        path_prefix=data.path_prefix,
    )
    assert categories.total_count == 6
    assert [(bucket.key, bucket.count) for bucket in categories.buckets] == [
        ("text", 3),
        ("image", 2),
        ("other", 1),
        ("unknown", 1),
    ]
    assert sum(bucket.count for bucket in categories.buckets) > (
        categories.total_count
    )

    exact = service.aggregate_resources(
        group_by="mime_type",
        observed_from=data.observed_from,
        observed_to=data.observed_to,
        path_prefix=data.path_prefix,
    )
    assert exact.total_count == 6
    assert exact.buckets[0].key == "text/markdown"
    assert exact.buckets[0].count == 3
    assert {bucket.key for bucket in exact.buckets} >= {
        "image/jpeg",
        "image/png",
        "malformed",
        "unknown",
    }


def test_source_mime_authority_conflicts_shared_blob_and_legacy_fallback(
    v02_context,
) -> None:
    _, repository, service, data = v02_context
    token = uuid4().hex
    path_prefix = f"/mime-authority/{token}"
    shared = Asset(
        title=f"Shared MIME {token}",
        created_at=data.now - timedelta(hours=1),
        updated_at=data.now - timedelta(hours=1),
    )
    false_image = Asset(
        title=f"False image {token}",
        created_at=data.now - timedelta(hours=2),
        updated_at=data.now - timedelta(hours=2),
    )
    legacy = Asset(
        title=f"Legacy MIME {token}",
        created_at=data.now - timedelta(hours=3),
        updated_at=data.now - timedelta(hours=3),
    )
    unknown = Asset(
        title=f"Unknown MIME {token}",
        created_at=data.now - timedelta(hours=4),
        updated_at=data.now - timedelta(hours=4),
    )
    shared_blob = Blob(
        asset_id=shared.id,
        hash=f"mime-shared-{token}",
        size=10,
        mime_type="application/octet-stream",
    )
    false_image_blob = Blob(
        asset_id=false_image.id,
        hash=f"mime-false-image-{token}",
        size=10,
        mime_type="image/jpeg",
    )
    legacy_blob = Blob(
        asset_id=legacy.id,
        hash=f"mime-legacy-{token}",
        size=10,
        mime_type="text/plain",
    )
    unknown_blob = Blob(
        asset_id=unknown.id,
        hash=f"mime-unknown-{token}",
        size=10,
        mime_type=None,
    )

    def source(
        blob: Blob,
        name: str,
        provider_mime_type: str | None,
    ) -> AssetSource:
        return AssetSource(
            blob_id=blob.id,
            provider=f"mime-provider-{name}",
            external_id=f"mime-source-{token}-{name}",
            path=f"{path_prefix}/{name}",
            name=name,
            provider_mime_type=provider_mime_type,
        )

    sources = (
        source(shared_blob, "source.py", "text/x-python"),
        source(shared_blob, "source.md", "text/markdown"),
        source(false_image_blob, "opaque.bin", "application/octet-stream"),
        source(legacy_blob, "legacy.txt", None),
        source(unknown_blob, "unknown.bin", None),
    )
    repository.execute(Decision(actions=[
        *(
            Action(type=ActionType.CREATE_ASSET, asset=asset)
            for asset in (shared, false_image, legacy, unknown)
        ),
        *(
            Action(type=ActionType.CREATE_BLOB, blob=blob)
            for blob in (
                shared_blob,
                false_image_blob,
                legacy_blob,
                unknown_blob,
            )
        ),
        *(
            Action(type=ActionType.CREATE_SOURCE, source=item)
            for item in sources
        ),
    ]))

    for mime_type, expected_ref in (
        ("text/x-python", format_resource_ref(shared.id)),
        ("text/markdown", format_resource_ref(shared.id)),
        ("application/octet-stream", format_resource_ref(false_image.id)),
        ("text/plain", format_resource_ref(legacy.id)),
    ):
        page = service.list_resource_page(
            days=10,
            mime_type=mime_type,
            path_prefix=path_prefix,
        )
        assert [item.resource_ref for item in page.resources] == [expected_ref]

    assert service.list_resource_page(
        days=10,
        mime_type="image/jpeg",
        path_prefix=path_prefix,
    ).resources == ()
    assert service.search_resource_page(
        query="opaque",
        mime_type="image/jpeg",
        path_prefix=path_prefix,
    ).resources == ()
    assert [item.resource_ref for item in service.search_resource_page(
        query="opaque",
        mime_type="application/octet-stream",
        path_prefix=path_prefix,
    ).resources] == [format_resource_ref(false_image.id)]
    assert [item.resource_ref for item in service.list_resource_page(
        days=10,
        mime_category="unknown",
        path_prefix=path_prefix,
    ).resources] == [format_resource_ref(unknown.id)]

    grouped = service.aggregate_resources(
        group_by="mime_type",
        observed_from=data.now - timedelta(days=1),
        observed_to=data.now,
        path_prefix=path_prefix,
    )
    assert {(bucket.key, bucket.count) for bucket in grouped.buckets} == {
        ("text/x-python", 1),
        ("text/markdown", 1),
        ("application/octet-stream", 1),
        ("text/plain", 1),
        ("unknown", 1),
    }
    detail = service.get_resource(format_resource_ref(shared.id))
    assert detail is not None
    assert {item.mime_type for item in detail.sources} == {
        "text/x-python",
        "text/markdown",
    }
    assert {item.mime_type for item in detail.content_variants} == {
        "application/octet-stream"
    }


def test_provider_counts_distinct_resources_and_same_source_filters(
    v02_context,
) -> None:
    _, _, service, data = v02_context
    providers = service.aggregate_resources(
        group_by="provider",
        observed_from=data.observed_from,
        observed_to=data.observed_to,
        path_prefix=data.path_prefix,
    )

    assert providers.total_count == 6
    assert [(bucket.key, bucket.count) for bucket in providers.buckets] == [
        (data.provider, 6),
        (data.alternate_provider, 1),
    ]
    assert sum(bucket.count for bucket in providers.buckets) == 7

    assert service.aggregate_resources(
        observed_from=data.observed_from,
        observed_to=data.observed_to,
        provider=data.alternate_provider,
        mime_category="text",
        path_prefix=data.path_prefix,
    ).total_count == 0
    image_match = service.aggregate_resources(
        observed_from=data.observed_from,
        observed_to=data.observed_to,
        provider=data.alternate_provider,
        mime_category="image",
        path_prefix=data.path_prefix,
    )
    assert image_match.total_count == 1


def test_recent_keyset_has_no_duplicates_ties_or_new_snapshot_rows(
    v02_context,
) -> None:
    _, repository, service, data = v02_context
    first_page = service.list_resource_page(
        days=10,
        provider=data.provider,
        path_prefix=data.path_prefix,
        limit=2,
    )
    assert first_page.next_cursor is not None

    inserted = Asset(
        title="Post Snapshot",
        created_at=data.now + timedelta(seconds=1),
        updated_at=data.now + timedelta(seconds=1),
    )
    source_actions, _ = _source_actions(
        asset=inserted,
        provider=data.provider,
        path=f"{data.path_prefix}/post-snapshot.txt",
        mime_type="text/plain",
    )
    repository.execute(
        Decision(
            actions=[
                Action(type=ActionType.CREATE_ASSET, asset=inserted),
                *source_actions,
            ]
        )
    )

    resources = list(first_page.resources)
    cursor = first_page.next_cursor
    while cursor is not None:
        page = service.list_resource_page(
            days=10,
            provider=data.provider,
            path_prefix=data.path_prefix,
            limit=2,
            cursor=cursor,
        )
        resources.extend(page.resources)
        cursor = page.next_cursor

    refs = tuple(resource.resource_ref for resource in resources)
    assert refs == data.expected_recent_refs
    assert len(refs) == len(set(refs))
    assert format_resource_ref(inserted.id) not in refs
    tied_positions = tuple(refs.index(ref) for ref in data.tied_refs)
    assert tied_positions[0] < tied_positions[1]


def test_search_keyset_preserves_substring_ties_and_range(v02_context) -> None:
    _, _, service, data = v02_context
    resources = []
    cursor = None
    while True:
        page = service.search_resource_page(
            query="SearchTie",
            observed_from=data.observed_from,
            observed_to=data.observed_to,
            provider=data.provider,
            path_prefix=data.path_prefix,
            limit=1,
            cursor=cursor,
        )
        resources.extend(page.resources)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert tuple(item.resource_ref for item in resources) == data.tied_refs
    assert len({item.resource_ref for item in resources}) == 2

    source_match = service.search_resource_page(
        query="multi-photo",
        observed_from=data.observed_from,
        observed_to=data.observed_to,
        provider=data.alternate_provider,
        mime_category="image",
        path_prefix=data.path_prefix,
    )
    assert [item.resource_ref for item in source_match.resources] == [
        data.multi_provider_ref
    ]


def test_provider_buckets_are_bounded_and_report_truncation(
    v02_context,
) -> None:
    _, repository, service, data = v02_context
    bucket_prefix = f"/query-v02-buckets/{uuid4().hex}"
    asset = Asset(
        title="Many Providers",
        created_at=data.now - timedelta(hours=1),
        updated_at=data.now - timedelta(hours=1),
    )
    actions = [Action(type=ActionType.CREATE_ASSET, asset=asset)]
    for index in range(101):
        source_actions, _ = _source_actions(
            asset=asset,
            provider=f"bucket-provider-{index:03d}",
            path=f"{bucket_prefix}/{index:03d}.txt",
            mime_type="text/plain",
        )
        actions.extend(source_actions)
    repository.execute(Decision(actions=actions))

    result = service.aggregate_resources(
        group_by=ResourceGroupBy.PROVIDER,
        observed_from=data.observed_from,
        observed_to=data.observed_to,
        path_prefix=bucket_prefix,
    )
    assert result.total_count == 1
    assert len(result.buckets) == 100
    assert result.buckets_truncated is True
    assert all(bucket.count == 1 for bucket in result.buckets)
    assert [bucket.key for bucket in result.buckets] == sorted(
        bucket.key for bucket in result.buckets
    )[:100]


def test_person_label_discovery_is_active_distinct_bounded_and_ocr_free(
    v02_context,
) -> None:
    database_url, _, service, data = v02_context
    token = uuid4().hex
    provider = f"person-label-discovery-{token}"
    bounded_provider = f"person-label-bound-{token}"
    now = datetime.now(UTC)
    people = [PersonORM(id=uuid4(), created_at=now) for _ in range(107)]
    sources = [
        PersonSourceORM(
            provider=provider,
            external_id=f"alice-a-{token}",
            person_id=people[0].id,
            display_name="Alice",
            inactive_at=None,
        ),
        PersonSourceORM(
            provider=provider,
            external_id=f"alice-duplicate-{token}",
            person_id=people[0].id,
            display_name="Alice",
            inactive_at=None,
        ),
        PersonSourceORM(
            provider=provider,
            external_id=f"alice-b-{token}",
            person_id=people[1].id,
            display_name="alice",
            inactive_at=None,
        ),
        PersonSourceORM(
            provider=provider,
            external_id=f"named-{token}",
            person_id=people[2].id,
            display_name="妈妈",
            inactive_at=None,
        ),
        PersonSourceORM(
            provider=provider,
            external_id=f"unnamed-{token}",
            person_id=people[3].id,
            display_name=None,
            inactive_at=None,
        ),
        PersonSourceORM(
            provider=provider,
            external_id=f"inactive-{token}",
            person_id=people[4].id,
            display_name="Inactive Label",
            inactive_at=now,
        ),
        PersonSourceORM(
            provider=provider,
            external_id=f"renamed-{token}",
            person_id=people[5].id,
            display_name="Current Label",
            inactive_at=None,
        ),
    ]
    sources.extend(
        PersonSourceORM(
            provider=bounded_provider,
            external_id=f"bounded-{index:03d}-{token}",
            person_id=people[index + 6].id,
            display_name=f"Label {index:03d}",
            inactive_at=None,
        )
        for index in range(101)
    )
    ocr_only_label = f"OCR Only {token}"
    statement = ResourceStatementORM(
        subject_asset_id=UUID(parse_resource_ref(data.multi_provider_ref)),
        predicate="media.ocr_text",
        value_type="string",
        string_value=ocr_only_label,
        generator_type="deterministic_extractor",
        generator_name="person-label-discovery-test",
        generator_version="1",
        source_kind="resource_content",
        source_locator=f"test:{token}",
        is_current=True,
    )
    engine = create_postgres_engine(database_url)
    statement_id = None
    person_ids = [person.id for person in people]
    try:
        with Session(engine) as session:
            session.add_all([*people, *sources, statement])
            session.commit()
            statement_id = statement.id

        first = service.aggregate_resources(
            group_by="person_label",
            provider=provider,
        )
        second = service.aggregate_resources(
            group_by="person_label",
            provider=provider,
        )
        assert first.time_basis == "current_person_source"
        assert first.total_count == 4
        assert first.buckets == second.buckets
        assert {bucket.key.lower(): bucket.count for bucket in first.buckets} == {
            "alice": 2,
            "current label": 1,
            "妈妈": 1,
        }
        assert all(bucket.key != "Inactive Label" for bucket in first.buckets)
        assert all(bucket.key != ocr_only_label for bucket in first.buckets)

        bounded = service.aggregate_resources(
            group_by=ResourceGroupBy.PERSON_LABEL,
            provider=bounded_provider,
        )
        assert bounded.total_count == 101
        assert len(bounded.buckets) == 100
        assert bounded.buckets_truncated is True
        assert [bucket.key for bucket in bounded.buckets] == [
            f"Label {index:03d}" for index in range(100)
        ]
        assert all(bucket.count == 1 for bucket in bounded.buckets)
    finally:
        with Session(engine) as session:
            if statement_id is not None:
                session.execute(
                    delete(ResourceStatementORM).where(
                        ResourceStatementORM.id == statement_id
                    )
                )
            session.execute(
                delete(PersonSourceORM).where(
                    PersonSourceORM.provider.in_(
                        (provider, bounded_provider)
                    )
                )
            )
            session.execute(
                delete(PersonORM).where(
                    PersonORM.id.in_(person_ids)
                )
            )
            session.commit()
        engine.dispose()


def test_mcp_v02_surface_serialization_and_postgresql(v02_context) -> None:
    database_url, _, _, data = v02_context
    server = create_runtime_server(database_url)

    async def exercise() -> None:
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            aggregation = await client.call_tool(
                "pdi_aggregate_resources",
                {
                    "group_by": "provider",
                    "observed_from": data.observed_from.isoformat(),
                    "observed_to": data.observed_to.isoformat(),
                    "path_prefix": data.path_prefix,
                },
            )
            person_labels = await client.call_tool(
                "pdi_aggregate_resources",
                {
                    "group_by": "person_label",
                    "provider": data.provider,
                },
            )
            recent = await client.call_tool(
                "pdi_list_recent_resources",
                {
                    "observed_from": data.observed_from.isoformat(),
                    "observed_to": data.observed_to.isoformat(),
                    "provider": data.provider,
                    "path_prefix": data.path_prefix,
                    "limit": 2,
                },
            )
            bounded = await client.call_tool(
                "pdi_query_resources",
                {
                    "primary": {
                        "kind": "path_tree",
                        "path_prefix": data.path_prefix,
                    },
                    "filters": {
                        "provider": data.provider,
                        "observed_from": data.observed_from.isoformat(),
                        "observed_to": data.observed_to.isoformat(),
                    },
                    "sort": {"basis": "path", "direction": "asc"},
                    "limit": 2,
                },
            )

        assert {tool.name for tool in tools} == {
            "pdi_list_recent_resources",
            "pdi_search_resources",
            "pdi_get_resource",
            "pdi_aggregate_resources",
            "pdi_get_resource_observations",
            "pdi_retrieve_resources",
            "pdi_rich_retrieve_resources",
            "pdi_get_data_status",
            "pdi_query_resources",
            "pdi_read_resource_text",
            "pdi_read_resource_image_preview",
        }
        payload = aggregation.structured_content
        assert payload is not None
        assert payload["ok"] is True
        assert payload["time_basis"] == "pdi_first_observed_at"
        assert payload["group_by"] == "provider"
        assert payload["total_count"] == 6
        assert payload["buckets_truncated"] is False
        label_payload = person_labels.structured_content
        assert label_payload is not None
        assert label_payload == {
            "ok": True,
            "time_basis": "current_person_source",
            "observed_from": None,
            "observed_to": None,
            "applied_filters": {
                "provider": data.provider,
                "resource_type": None,
                "mime_type": None,
                "mime_category": None,
                "path_prefix": None,
            },
            "group_by": "person_label",
            "total_count": 0,
            "buckets": [],
            "buckets_truncated": False,
        }
        encoded = json.dumps(payload)
        for internal_name in (
            "asset_id",
            "blob_id",
            "source_id",
            "external_id",
            "metadata",
            "raw",
        ):
            assert internal_name not in encoded

        recent_payload = recent.structured_content
        assert recent_payload is not None
        assert "resources" in recent_payload
        assert recent_payload["next_cursor"] is not None

        bounded_payload = bounded.structured_content
        assert bounded_payload is not None
        assert bounded_payload["ok"] is True
        assert bounded_payload["schema"] == "pdi.resource-list.v1"
        assert bounded_payload["query_kind"] == "path_tree"
        assert bounded_payload["selection_status"] == "complete"
        assert bounded_payload["continuation"] is None
        assert len(bounded_payload["resources"]) == 2
        assert all(
            resource["relative_path"].startswith(
                data.path_prefix.removeprefix("/") + "/"
            )
            for resource in bounded_payload["resources"]
        )
        bounded_encoded = json.dumps(bounded_payload)
        for internal_name in (
            "sources",
            "observations",
            "external_id",
            "provider_locator",
            "metadata",
            "raw",
        ):
            assert f'"{internal_name}"' not in bounded_encoded

    asyncio.run(exercise())
