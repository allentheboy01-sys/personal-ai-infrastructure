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
from sqlalchemy import Connection, Engine, event

from pdi.database import create_postgres_engine
from pdi.decision import Action, ActionType, Decision
from pdi.models import Asset, AssetSource, Blob, ResourceType
from pdi.query import (
    QueryService,
    ResourceDetail,
    ResourceNotFoundError,
    ResourceSummary,
    format_resource_ref,
)
from pdi.repository import PostgreSQLRepository
from pdi_mcp.bootstrap import create_runtime_server
from tests.integration.database_guard import (
    require_safe_test_database_url,
)


ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class QueryTestData:
    now: datetime
    provider: str
    alternate_provider: str
    boundary_asset: Asset
    first_tied_asset: Asset
    second_tied_asset: Asset
    old_asset: Asset
    inactive_asset: Asset
    zero_source_asset: Asset
    cross_filter_asset: Asset
    cross_filter_path_prefix: str
    cross_filter_source_query: str
    detail_hashes: frozenset[str]


def _alembic_config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def _upgrade_schema(engine: Engine) -> None:
    with engine.connect() as connection:
        command.upgrade(_alembic_config(connection), "head")


def _create_source(
    *,
    asset: Asset,
    provider: str,
    name: str,
    path: str,
    mime_type: str,
    size: int,
    active: bool = True,
) -> tuple[Blob, AssetSource]:
    blob = Blob(
        asset_id=asset.id,
        hash=f"query-sha256-{uuid4()}",
        size=size,
        mime_type=mime_type,
    )
    source = AssetSource(
        blob_id=blob.id,
        provider=provider,
        external_id=f"query-source-{uuid4()}",
        path=path,
        name=name,
        is_active=active,
        deleted_at=None if active else datetime.now(UTC),
    )
    return blob, source


def _create_test_data(
    repository: PostgreSQLRepository,
) -> QueryTestData:
    now = datetime.now(UTC)
    token = uuid4().hex
    provider = f"query-test-{token}"
    alternate_provider = f"query-alt-{token}"
    tied_ids = sorted((uuid4(), uuid4()))

    boundary_asset = Asset(
        title=f"Boundary {token}",
        created_at=now - timedelta(days=7),
        updated_at=now - timedelta(days=7),
    )
    first_tied_asset = Asset(
        id=str(tied_ids[0]),
        title=f"CURRENT_CONTEXT {token}",
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
    )
    second_tied_asset = Asset(
        id=str(tied_ids[1]),
        title=f"Second {token}",
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
    )
    old_asset = Asset(
        title=f"Old {token}",
        created_at=now - timedelta(days=8),
        updated_at=now - timedelta(days=8),
    )
    inactive_asset = Asset(
        title=f"Inactive searchable {token}",
        created_at=now,
        updated_at=now,
    )
    zero_source_asset = Asset(
        title=f"Zero source {token}",
        created_at=now,
        updated_at=now,
    )
    cross_filter_asset = Asset(
        title=f"Cross Source Filter {token}",
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
    )

    boundary_blob, boundary_source = _create_source(
        asset=boundary_asset,
        provider=provider,
        name=f"boundary-{token}.txt",
        path=f"/query/{token}/boundary.txt",
        mime_type="text/plain",
        size=100,
    )
    detail_blob, detail_source = _create_source(
        asset=first_tied_asset,
        provider=provider,
        name=f"SOURCE_NAME_{token}.md",
        path=f"/query/{token}/docs/CURRENT_CONTEXT.md",
        mime_type="text/markdown",
        size=200,
    )
    alternate_blob, alternate_source = _create_source(
        asset=first_tied_asset,
        provider=alternate_provider,
        name=f"photo-{token}.jpg",
        path=f"/query/{token}/photos/photo.jpg",
        mime_type="image/jpeg",
        size=300,
    )
    inactive_detail_blob, inactive_detail_source = _create_source(
        asset=first_tied_asset,
        provider=provider,
        name=f"archived-{token}.bin",
        path=f"/query/{token}/archive/item.bin",
        mime_type="application/octet-stream",
        size=400,
        active=False,
    )
    second_blob, second_source = _create_source(
        asset=second_tied_asset,
        provider=provider,
        name=f"second-{token}.txt",
        path=f"/query/{token}/second.txt",
        mime_type="text/plain",
        size=500,
    )
    old_blob, old_source = _create_source(
        asset=old_asset,
        provider=provider,
        name=f"old-{token}.txt",
        path=f"/query/{token}/old.txt",
        mime_type="text/plain",
        size=600,
    )
    inactive_blob, inactive_source = _create_source(
        asset=inactive_asset,
        provider=provider,
        name=f"inactive-searchable-{token}.txt",
        path=f"/query/{token}/inactive-searchable.txt",
        mime_type="text/plain",
        size=700,
        active=False,
    )
    cross_filter_path_prefix = f"/query/{token}/cross-filter"
    cross_markdown_blob, cross_markdown_source = _create_source(
        asset=cross_filter_asset,
        provider="nextcloud",
        name=f"cross-note-{token}.md",
        path=f"{cross_filter_path_prefix}/note.md",
        mime_type="text/markdown",
        size=800,
    )
    cross_photo_blob, cross_photo_source = _create_source(
        asset=cross_filter_asset,
        provider="immich",
        name=f"cross-photo-{token}.jpg",
        path=f"{cross_filter_path_prefix}/photo.jpg",
        mime_type="image/jpeg",
        size=900,
    )

    assets = (
        boundary_asset,
        first_tied_asset,
        second_tied_asset,
        old_asset,
        inactive_asset,
        zero_source_asset,
        cross_filter_asset,
    )
    blobs = (
        boundary_blob,
        detail_blob,
        alternate_blob,
        inactive_detail_blob,
        second_blob,
        old_blob,
        inactive_blob,
        cross_markdown_blob,
        cross_photo_blob,
    )
    sources = (
        boundary_source,
        detail_source,
        alternate_source,
        inactive_detail_source,
        second_source,
        old_source,
        inactive_source,
        cross_markdown_source,
        cross_photo_source,
    )
    actions = [
        Action(type=ActionType.CREATE_ASSET, asset=asset)
        for asset in assets
    ]
    actions.extend(
        Action(type=ActionType.CREATE_BLOB, blob=blob)
        for blob in blobs
    )
    actions.extend(
        Action(type=ActionType.CREATE_SOURCE, source=source)
        for source in sources
    )
    repository.execute(Decision(actions=actions))

    return QueryTestData(
        now=now,
        provider=provider,
        alternate_provider=alternate_provider,
        boundary_asset=boundary_asset,
        first_tied_asset=first_tied_asset,
        second_tied_asset=second_tied_asset,
        old_asset=old_asset,
        inactive_asset=inactive_asset,
        zero_source_asset=zero_source_asset,
        cross_filter_asset=cross_filter_asset,
        cross_filter_path_prefix=cross_filter_path_prefix,
        cross_filter_source_query=f"cross-photo-{token}",
        detail_hashes=frozenset(
            {
                detail_blob.hash,
                alternate_blob.hash,
                inactive_detail_blob.hash,
            }
        ),
    )


@pytest.fixture(scope="module")
def query_context():
    engine = create_postgres_engine(require_safe_test_database_url())
    _upgrade_schema(engine)
    repository = PostgreSQLRepository(engine)
    data = _create_test_data(repository)
    service = QueryService(repository, clock=lambda: data.now)

    try:
        yield engine, repository, service, data
    finally:
        engine.dispose()


def test_recent_uses_creation_boundary_stable_order_and_limit(
    query_context,
) -> None:
    engine, _, service, data = query_context
    select_statements: list[str] = []

    def record_select(_, __, statement, *args) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_select)
    try:
        resources = service.list_recent_resources(
            days=7,
            provider=data.provider,
            limit=3,
        )
    finally:
        event.remove(engine, "before_cursor_execute", record_select)

    assert [
        resource.resource_ref for resource in resources
    ] == [
        format_resource_ref(data.first_tied_asset.id),
        format_resource_ref(data.second_tied_asset.id),
        format_resource_ref(data.boundary_asset.id),
    ]
    assert len(select_statements) == 3
    assert all(isinstance(resource, ResourceSummary) for resource in resources)
    assert all(source.is_active for item in resources for source in item.sources)
    assert format_resource_ref(data.old_asset.id) not in {
        resource.resource_ref for resource in resources
    }
    assert format_resource_ref(data.inactive_asset.id) not in {
        resource.resource_ref for resource in resources
    }
    assert len(
        service.list_recent_resources(
            days=7,
            provider=data.provider,
            limit=2,
        )
    ) == 2


def test_search_matches_metadata_and_applies_source_filters(
    query_context,
) -> None:
    _, _, service, data = query_context
    target_ref = format_resource_ref(data.first_tied_asset.id)
    token = data.provider.removeprefix("query-test-")

    for query in (
        "CURRENT_CONTEXT",
        f"SOURCE_NAME_{token}",
        f"docs/CURRENT_CONTEXT",
    ):
        results = service.search_resources(
            query=query,
            provider=data.provider,
        )
        assert target_ref in {
            resource.resource_ref for resource in results
        }

    filtered = service.search_resources(
        query="CURRENT_CONTEXT",
        provider=data.provider,
        mime_type="text/markdown",
        path_prefix=f"/query/{token}/docs",
    )
    assert [item.resource_ref for item in filtered] == [target_ref]

    assert service.search_resources(
        query="CURRENT_CONTEXT",
        provider=data.alternate_provider,
        mime_type="text/markdown",
    ) == ()

    # Source-level filters must be satisfied by one active Source and
    # its current Blob. They cannot be assembled across Sources.
    assert service.search_resources(
        query="CURRENT_CONTEXT",
        provider=data.provider,
        mime_type="image/jpeg",
    ) == ()
    same_source_match = service.search_resources(
        query="CURRENT_CONTEXT",
        provider=data.alternate_provider,
        mime_type="image/jpeg",
    )
    assert [item.resource_ref for item in same_source_match] == [
        target_ref
    ]

    assert service.list_recent_resources(
        days=7,
        provider=data.provider,
        mime_type="image/jpeg",
    ) == ()
    assert target_ref in {
        item.resource_ref
        for item in service.list_recent_resources(
            days=7,
            provider=data.alternate_provider,
            mime_type="image/jpeg",
        )
    }
    assert service.search_resources(
        query="inactive-searchable",
        provider=data.provider,
    ) == ()

    cross_filter_ref = format_resource_ref(data.cross_filter_asset.id)
    assert service.list_recent_resources(
        days=7,
        provider="nextcloud",
        mime_type="image/jpeg",
        path_prefix=data.cross_filter_path_prefix,
    ) == ()
    same_source_recent = service.list_recent_resources(
        days=7,
        provider="immich",
        mime_type="image/jpeg",
        path_prefix=data.cross_filter_path_prefix,
    )
    assert [item.resource_ref for item in same_source_recent] == [
        cross_filter_ref
    ]

    assert service.search_resources(
        query=data.cross_filter_source_query,
        provider="nextcloud",
        mime_type="image/jpeg",
        path_prefix=data.cross_filter_path_prefix,
    ) == ()
    same_source_search = service.search_resources(
        query=data.cross_filter_source_query,
        provider="immich",
        mime_type="image/jpeg",
        path_prefix=data.cross_filter_path_prefix,
    )
    assert [item.resource_ref for item in same_source_search] == [
        cross_filter_ref
    ]


def test_detail_is_complete_detached_and_distinguishes_missing(
    query_context,
) -> None:
    _, _, service, data = query_context
    detail = service.get_resource(
        format_resource_ref(data.first_tied_asset.id)
    )

    assert isinstance(detail, ResourceDetail)
    assert len(detail.sources) == 3
    assert {source.is_active for source in detail.sources} == {True, False}
    assert len({source.provider for source in detail.sources}) == 2
    assert {item.checksum for item in detail.content_variants} == (
        data.detail_hashes
    )
    assert all(not isinstance(item, Asset) for item in detail.sources)

    zero_source_detail = service.get_resource(
        format_resource_ref(data.zero_source_asset.id)
    )
    assert zero_source_detail.sources == ()
    assert zero_source_detail.content_variants == ()

    with pytest.raises(ResourceNotFoundError):
        service.get_resource(format_resource_ref(UUID(int=0)))


def test_query_returns_and_filters_stored_resource_type(
    query_context,
) -> None:
    _, repository, service, data = query_context
    token = uuid4().hex
    message = Asset(
        resource_type=ResourceType.MESSAGE,
        title=f"Typed message {token}",
        created_at=data.now - timedelta(seconds=1),
        updated_at=data.now - timedelta(seconds=1),
    )
    blob, source = _create_source(
        asset=message,
        provider=f"typed-message-{token}",
        name="message.eml",
        path="",
        mime_type="message/rfc822",
        size=256,
    )
    repository.execute(Decision(actions=[
        Action(type=ActionType.CREATE_ASSET, asset=message),
        Action(type=ActionType.CREATE_BLOB, blob=blob),
        Action(type=ActionType.CREATE_SOURCE, source=source),
    ]))

    message_results = service.list_recent_resources(
        days=1,
        resource_type="message",
        provider=source.provider,
    )
    assert [item.resource_type for item in message_results] == [
        "message"
    ]
    assert service.list_recent_resources(
        days=1,
        resource_type="file",
        provider=source.provider,
    ) == ()
    assert service.get_resource(
        format_resource_ref(message.id)
    ).resource_type == "message"


def test_mcp_client_reaches_real_postgresql_without_id_leaks(
    query_context,
) -> None:
    _, _, _, data = query_context
    database_url = require_safe_test_database_url()
    server = create_runtime_server(database_url)
    target_ref = format_resource_ref(data.first_tied_asset.id)
    zero_source_ref = format_resource_ref(data.zero_source_asset.id)

    async def exercise_tools() -> None:
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            recent = await client.call_tool(
                "pdi_list_recent_resources",
                {
                    "days": 30,
                    "provider": data.provider,
                    "limit": 10,
                },
            )
            search = await client.call_tool(
                "pdi_search_resources",
                {
                    "query": "CURRENT_CONTEXT",
                    "provider": data.provider,
                },
            )
            detail = await client.call_tool(
                "pdi_get_resource",
                {"resource_ref": target_ref},
            )
            zero_source = await client.call_tool(
                "pdi_get_resource",
                {"resource_ref": zero_source_ref},
            )
            invalid_ref = await client.call_tool(
                "pdi_get_resource",
                {"resource_ref": "pdi:resource:invalid"},
            )
            missing = await client.call_tool(
                "pdi_get_resource",
                {"resource_ref": format_resource_ref(UUID(int=0))},
            )

        recent_payload = recent.structured_content
        search_payload = search.structured_content
        detail_payload = detail.structured_content
        zero_source_payload = zero_source.structured_content
        assert recent_payload is not None
        assert search_payload is not None
        assert detail_payload is not None
        assert zero_source_payload is not None
        assert target_ref in {
            item["resource_ref"]
            for item in recent_payload["resources"]
        }
        assert [
            item["resource_ref"]
            for item in search_payload["resources"]
        ] == [target_ref]

        projected_resource = detail_payload["resource"]
        assert projected_resource["resource_ref"] == target_ref
        assert len(projected_resource["sources"]) == 3
        assert {source["is_active"] for source in projected_resource[
            "sources"
        ]} == {True, False}
        assert zero_source_payload["resource"]["sources"] == []

        public_payload = json.dumps(
            [recent_payload, search_payload, detail_payload]
        )
        assert "checksum" not in json.dumps(recent_payload)
        assert "checksum" not in json.dumps(search_payload)
        for forbidden_name in (
            "asset_id",
            "blob_id",
            "source_id",
            "external_id",
            "metadata",
            "raw",
            "primary_source",
        ):
            assert forbidden_name not in public_payload

        recent_tool = next(
            tool
            for tool in tools
            if tool.name == "pdi_list_recent_resources"
        )
        assert recent_tool.description is not None
        assert "when PDI first created" in recent_tool.description
        assert invalid_ref.structured_content["error"]["code"] == (
            "invalid_resource_ref"
        )
        assert missing.structured_content["error"]["code"] == (
            "resource_not_found"
        )

    asyncio.run(exercise_tools())
