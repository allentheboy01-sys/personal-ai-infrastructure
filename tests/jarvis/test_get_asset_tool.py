from datetime import UTC, datetime
from uuid import uuid4

import pytest

from jarvis import JarvisApplication, ToolCall
from jarvis.tools import GetAssetTool, ToolRegistry
from pdi.query import AssetDetail


class StubQueryService:
    def __init__(self, asset: AssetDetail | None) -> None:
        self.asset = asset
        self.requested_ids: list[str] = []

    def get_asset(self, asset_id: str) -> AssetDetail | None:
        self.requested_ids.append(asset_id)
        return self.asset


class FailingQueryService:
    def get_asset(self, asset_id: str) -> AssetDetail | None:
        raise RuntimeError("query failed")


def _detail(asset_id: str) -> AssetDetail:
    observed_at = datetime(2026, 7, 22, tzinfo=UTC)
    return AssetDetail(
        id=asset_id,
        title="Photo",
        metadata={},
        created_at=observed_at,
        updated_at=observed_at,
        blobs=(),
        sources=(),
    )


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"asset_id": 123},
        {"asset_id": "not-a-uuid"},
        {"asset_id": str(uuid4()), "extra": True},
    ],
)
def test_get_asset_rejects_invalid_arguments(arguments) -> None:
    service = StubQueryService(None)
    tool = GetAssetTool(service)

    result = tool.execute(arguments)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "invalid_arguments"
    assert service.requested_ids == []


def test_get_asset_returns_asset_detail() -> None:
    asset_id = str(uuid4())
    detail = _detail(asset_id)
    service = StubQueryService(detail)
    tool = GetAssetTool(service)

    result = tool.execute({"asset_id": asset_id})

    assert result.success is True
    assert result.data is detail
    assert service.requested_ids == [asset_id]


def test_get_asset_converts_missing_asset_to_business_error() -> None:
    asset_id = str(uuid4())
    tool = GetAssetTool(StubQueryService(None))

    result = tool.execute({"asset_id": asset_id})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "asset_not_found"


def test_get_asset_service_exception_reaches_application_boundary() -> None:
    registry = ToolRegistry()
    registry.register(GetAssetTool(FailingQueryService()))
    application = JarvisApplication(registry)

    result = application.execute(
        ToolCall(
            name="get_asset",
            arguments={"asset_id": str(uuid4())},
        )
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "internal_error"
