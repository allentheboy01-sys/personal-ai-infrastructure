from datetime import UTC, datetime

import pytest

from jarvis.tools import ListAssetsTool
from pdi.query import AssetSummary


class StubQueryService:
    def __init__(
        self,
        assets: tuple[AssetSummary, ...],
    ) -> None:
        self.assets = assets
        self.call_count = 0

    def list_assets(self) -> tuple[AssetSummary, ...]:
        self.call_count += 1
        return self.assets


class FailingQueryService:
    def list_assets(self) -> tuple[AssetSummary, ...]:
        raise RuntimeError("query failed")


def _summary() -> AssetSummary:
    observed_at = datetime(2026, 7, 22, tzinfo=UTC)
    return AssetSummary(
        id="asset-1",
        title="Photo",
        created_at=observed_at,
        updated_at=observed_at,
    )


def test_list_assets_returns_query_service_results() -> None:
    summary = _summary()
    service = StubQueryService((summary,))
    tool = ListAssetsTool(service)

    result = tool.execute({})

    assert result.success is True
    assert result.data == (summary,)
    assert isinstance(result.data, tuple)
    assert service.call_count == 1


def test_list_assets_returns_success_for_empty_database() -> None:
    tool = ListAssetsTool(StubQueryService(()))

    result = tool.execute({})

    assert result.success is True
    assert result.data == ()


def test_list_assets_rejects_unknown_arguments() -> None:
    service = StubQueryService(())
    tool = ListAssetsTool(service)

    result = tool.execute({"limit": 10})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "invalid_arguments"
    assert service.call_count == 0


def test_list_assets_does_not_hide_service_exception() -> None:
    tool = ListAssetsTool(FailingQueryService())

    with pytest.raises(RuntimeError, match="query failed"):
        tool.execute({})
