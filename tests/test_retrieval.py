from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import requests

from pdi.query import InvalidQueryError, ResourceSummary, format_resource_ref
from pdi.retrieval import (
    ProviderCapabilityUnavailableError,
    ProviderInvalidResponseError,
    ProviderRetrievalHit,
    ProviderUnavailableError,
    RetrievalMappingError,
    RetrievalService,
)
from pdi.retrieval.providers import ImmichSemanticRetrievalAdapter


class FakeResponse:
    def __init__(
        self,
        payload: object = None,
        *,
        status_code: int = 200,
        json_error: Exception | None = None,
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError(response=response)

    def json(self) -> object:
        if self.json_error is not None:
            raise self.json_error
        return self.payload


def _adapter() -> ImmichSemanticRetrievalAdapter:
    return ImmichSemanticRetrievalAdapter(
        "https://immich.example/",
        "sensitive-api-key",
    )


def test_immich_retrieval_preserves_order_rank_and_deduplicates(
    monkeypatch,
) -> None:
    request: dict[str, object] = {}

    def fake_post(url: str, **kwargs) -> FakeResponse:
        request.update({"url": url, **kwargs})
        return FakeResponse({
            "assets": {
                "items": [
                    {"id": "asset-a", "ignored": "payload"},
                    {"id": "asset-b"},
                    {"id": "asset-a"},
                    {"id": "asset-c"},
                ]
            }
        })

    monkeypatch.setattr(
        "pdi.retrieval.providers.immich.requests.post",
        fake_post,
    )

    hits = _adapter().search_resources(query="  seaside  ", limit=5)

    assert request == {
        "url": "https://immich.example/api/search/smart",
        "headers": {"x-api-key": "sensitive-api-key"},
        "json": {"query": "  seaside  ", "page": 1, "size": 5},
        "timeout": (3, 7),
    }
    assert [hit.provider_locator for hit in hits] == [
        "asset-a",
        "asset-b",
        "asset-c",
    ]
    assert [hit.rank for hit in hits] == [1, 2, 4]
    assert all(hit.provider == "immich" for hit in hits)
    assert all(hit.provider_score is None for hit in hits)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"assets": []},
        {"assets": {}},
        {"assets": {"items": [None]}},
        {"assets": {"items": [{}]}},
        {"assets": {"items": [{"id": ""}]}},
    ],
)
def test_immich_retrieval_rejects_invalid_response(
    monkeypatch,
    payload,
) -> None:
    monkeypatch.setattr(
        "pdi.retrieval.providers.immich.requests.post",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    with pytest.raises(ProviderInvalidResponseError):
        _adapter().search_resources(query="photo", limit=5)


def test_immich_retrieval_rejects_malformed_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "pdi.retrieval.providers.immich.requests.post",
        lambda *args, **kwargs: FakeResponse(
            json_error=ValueError("malformed")
        ),
    )

    with pytest.raises(ProviderInvalidResponseError):
        _adapter().search_resources(query="photo", limit=5)


@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [
        (requests.Timeout(), ProviderUnavailableError),
        (requests.ConnectionError(), ProviderUnavailableError),
    ],
)
def test_immich_retrieval_maps_network_errors_without_secret_leakage(
    monkeypatch,
    failure,
    expected_error,
) -> None:
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(
        "pdi.retrieval.providers.immich.requests.post",
        fail,
    )

    with pytest.raises(expected_error) as captured:
        _adapter().search_resources(query="photo", limit=5)

    assert "sensitive-api-key" not in str(captured.value)


@pytest.mark.parametrize(
    ("status", "expected_error"),
    [
        (400, ProviderCapabilityUnavailableError),
        (404, ProviderCapabilityUnavailableError),
        (422, ProviderCapabilityUnavailableError),
        (500, ProviderUnavailableError),
        (503, ProviderUnavailableError),
    ],
)
def test_immich_retrieval_maps_http_errors(
    monkeypatch,
    status,
    expected_error,
) -> None:
    monkeypatch.setattr(
        "pdi.retrieval.providers.immich.requests.post",
        lambda *args, **kwargs: FakeResponse(status_code=status),
    )

    with pytest.raises(expected_error):
        _adapter().search_resources(query="photo", limit=5)


def _summary(name: str) -> ResourceSummary:
    return ResourceSummary(
        resource_ref=format_resource_ref(uuid4()),
        resource_type="file",
        display_name=name,
        pdi_first_observed_at=datetime(2026, 8, 14, tzinfo=UTC),
        sources=(),
    )


class StubProviderAdapter:
    provider = "immich"

    def __init__(self, hits: tuple[ProviderRetrievalHit, ...]) -> None:
        self.hits = hits
        self.calls: list[tuple[str, int]] = []

    def search_resources(
        self,
        *,
        query: str,
        limit: int,
    ) -> tuple[ProviderRetrievalHit, ...]:
        self.calls.append((query, limit))
        return self.hits


class StubMappingRepository:
    def __init__(self, mappings) -> None:
        self.mappings = mappings
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def map_active_resources(
        self,
        *,
        provider: str,
        provider_locators: tuple[str, ...],
    ):
        self.calls.append((provider, provider_locators))
        return self.mappings


def test_retrieval_service_maps_once_and_preserves_rank_gaps() -> None:
    first = _summary("first.jpg")
    third = _summary("third.jpg")
    provider_adapter = StubProviderAdapter((
        ProviderRetrievalHit("immich", "one", 1),
        ProviderRetrievalHit("immich", "missing", 2),
        ProviderRetrievalHit("immich", "three", 3),
    ))
    repository = StubMappingRepository({
        "one": (first,),
        "three": (third,),
    })
    service = RetrievalService(provider_adapter, repository)

    result = service.retrieve_resources(
        query="  seaside  ",
        provider="immich",
        limit=3,
    )

    assert provider_adapter.calls == [("seaside", 3)]
    assert repository.calls == [(
        "immich",
        ("one", "missing", "three"),
    )]
    assert [hit.rank for hit in result.hits] == [1, 3]
    assert [hit.resource for hit in result.hits] == [first, third]
    assert result.provider == "immich"
    assert result.retrieval_kind == "semantic"
    assert result.unmapped_hit_count == 1

    with pytest.raises(FrozenInstanceError):
        result.unmapped_hit_count = 0


def test_retrieval_service_rejects_ambiguous_mapping() -> None:
    provider_adapter = StubProviderAdapter((
        ProviderRetrievalHit("immich", "ambiguous", 1),
    ))
    repository = StubMappingRepository({
        "ambiguous": (_summary("one"), _summary("two")),
    })

    with pytest.raises(RetrievalMappingError):
        RetrievalService(
            provider_adapter,
            repository,
        ).retrieve_resources(
            query="photo",
            provider="immich",
        )


@pytest.mark.parametrize(
    ("query", "provider", "limit"),
    [
        ("", "immich", 20),
        ("   ", "immich", 20),
        (None, "immich", 20),
        ("photo", "nextcloud", 20),
        ("photo", "immich", 0),
        ("photo", "immich", 101),
        ("photo", "immich", True),
    ],
)
def test_retrieval_service_validates_public_arguments(
    query,
    provider,
    limit,
) -> None:
    service = RetrievalService(
        StubProviderAdapter(()),
        StubMappingRepository({}),
    )

    with pytest.raises(InvalidQueryError):
        service.retrieve_resources(
            query=query,
            provider=provider,
            limit=limit,
        )
