from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from pdi.query import (
    AssetDetail,
    AssetSummary,
    BlobView,
    QueryService,
    SourceView,
)


def _read_models() -> tuple[
    AssetSummary,
    AssetDetail,
]:
    observed_at = datetime(2026, 7, 21, tzinfo=UTC)
    summary = AssetSummary(
        id="asset-1",
        title="Photo",
        created_at=observed_at,
        updated_at=observed_at,
    )
    blob = BlobView(
        id="blob-1",
        asset_id=summary.id,
        hash="sha256-value",
        size=1024,
        mime_type="image/jpeg",
    )
    source = SourceView(
        id="source-1",
        blob_id=blob.id,
        provider="immich",
        external_id="immich-asset-1",
        path="/library/photo.jpg",
        name="photo.jpg",
        version_tag="v1",
        metadata={
            "favorite": True,
        },
        is_active=True,
        deleted_at=None,
    )
    detail = AssetDetail(
        id=summary.id,
        title=summary.title,
        metadata={
            "nested": {
                "labels": ["photo", "favorite"],
            },
        },
        created_at=summary.created_at,
        updated_at=summary.updated_at,
        blobs=(blob,),
        sources=(source,),
    )

    return summary, detail


class StubQueryRepository:
    def __init__(
        self,
        summary: AssetSummary,
        detail: AssetDetail,
    ) -> None:
        self.summary = summary
        self.detail = detail
        self.requested_asset_ids: list[str] = []

    def list_asset_summaries(
        self,
    ) -> tuple[AssetSummary, ...]:
        return (self.summary,)

    def get_asset_detail(
        self,
        asset_id: str,
    ) -> AssetDetail | None:
        self.requested_asset_ids.append(asset_id)

        if asset_id != self.detail.id:
            return None

        return self.detail


class EmptyQueryRepository:
    def list_asset_summaries(
        self,
    ) -> tuple[AssetSummary, ...]:
        return ()

    def get_asset_detail(
        self,
        asset_id: str,
    ) -> AssetDetail | None:
        return None


def test_query_service_delegates_to_repository() -> None:
    summary, detail = _read_models()
    repository = StubQueryRepository(summary, detail)
    service = QueryService(repository)

    assert service.list_assets() == (summary,)
    assert service.get_asset(detail.id) is detail
    assert service.get_asset("missing") is None
    assert repository.requested_asset_ids == [
        detail.id,
        "missing",
    ]


def test_query_service_preserves_empty_results() -> None:
    service = QueryService(EmptyQueryRepository())

    assert service.list_assets() == ()
    assert isinstance(service.list_assets(), tuple)
    assert service.get_asset("missing") is None


def test_read_models_are_immutable() -> None:
    summary, detail = _read_models()

    with pytest.raises(FrozenInstanceError):
        summary.title = "Changed"

    with pytest.raises(TypeError):
        detail.metadata["new"] = "value"

    nested = detail.metadata["nested"]

    assert isinstance(nested, Mapping)

    with pytest.raises(TypeError):
        nested["new"] = "value"

    assert nested["labels"] == (
        "photo",
        "favorite",
    )
    assert isinstance(detail.blobs, tuple)
    assert isinstance(detail.sources, tuple)
    assert isinstance(
        detail.sources[0].metadata,
        Mapping,
    )


def test_metadata_is_recursively_frozen_and_detached() -> None:
    observed_at = datetime(2026, 7, 21, tzinfo=UTC)
    asset_metadata = {
        "nested": {
            "items": [
                {
                    "value": "original",
                },
            ],
            "tuple_items": (
                {
                    "value": "tuple-original",
                },
            ),
        },
    }
    source_metadata = {
        "provider": {
            "values": [1, 2],
        },
    }
    source = SourceView(
        id="source-1",
        blob_id="blob-1",
        provider="immich",
        external_id="immich-asset-1",
        path=None,
        name=None,
        version_tag=None,
        metadata=source_metadata,
        is_active=True,
        deleted_at=None,
    )
    detail = AssetDetail(
        id="asset-1",
        title="Photo",
        metadata=asset_metadata,
        created_at=observed_at,
        updated_at=observed_at,
        blobs=(),
        sources=(source,),
    )

    asset_metadata["nested"]["items"][0][
        "value"
    ] = "changed"
    asset_metadata["nested"]["tuple_items"][0][
        "value"
    ] = "tuple-changed"
    source_metadata["provider"]["values"].append(3)

    frozen_nested = detail.metadata["nested"]
    frozen_item = frozen_nested["items"][0]
    frozen_tuple_item = frozen_nested[
        "tuple_items"
    ][0]
    frozen_source_values = detail.sources[0].metadata[
        "provider"
    ]["values"]

    assert isinstance(frozen_nested, Mapping)
    assert isinstance(frozen_item, Mapping)
    assert isinstance(frozen_tuple_item, Mapping)
    assert frozen_item["value"] == "original"
    assert frozen_tuple_item["value"] == "tuple-original"
    assert frozen_source_values == (1, 2)

    with pytest.raises(TypeError):
        frozen_item["value"] = "changed"

    with pytest.raises(TypeError):
        frozen_tuple_item["value"] = "changed"
