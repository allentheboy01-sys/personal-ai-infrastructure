import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from mcp import Client
import pytest
from sqlalchemy import Connection, Engine

from pdi.database import create_postgres_engine
from pdi.decision import Action, ActionType, Decision
from pdi.models import Asset, AssetSource, Blob
from pdi.query import QueryService, ResourceGroupBy, format_resource_ref
from pdi.repository import PostgreSQLRepository
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
            recent = await client.call_tool(
                "pdi_list_recent_resources",
                {
                    "days": 10,
                    "provider": data.provider,
                    "path_prefix": data.path_prefix,
                    "limit": 2,
                },
            )

        assert {tool.name for tool in tools} == {
            "pdi_list_recent_resources",
            "pdi_search_resources",
            "pdi_get_resource",
            "pdi_aggregate_resources",
        }
        payload = aggregation.structured_content
        assert payload is not None
        assert payload["ok"] is True
        assert payload["time_basis"] == "pdi_first_observed_at"
        assert payload["group_by"] == "provider"
        assert payload["total_count"] == 6
        assert payload["buckets_truncated"] is False
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

    asyncio.run(exercise())
