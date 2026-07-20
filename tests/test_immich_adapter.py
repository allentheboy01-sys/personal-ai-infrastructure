import logging

import pytest
import requests

from pdi.adapters.base import ProviderFact
from pdi.adapters.immich import ImmichAdapter


class FakeResponse:
    def __init__(
        self,
        *,
        json_data: object | None = None,
        chunks: tuple[bytes, ...] = (),
    ) -> None:
        self.json_data = json_data
        self.chunks = chunks
        self.raise_for_status_called = False
        self.closed = False

    def raise_for_status(self) -> None:
        self.raise_for_status_called = True

    def json(self) -> object:
        return self.json_data

    def iter_content(
        self,
        *,
        chunk_size: int,
    ) -> tuple[bytes, ...]:
        assert chunk_size == 1024 * 1024
        return self.chunks

    def close(self) -> None:
        self.closed = True


def test_connect_verifies_api_key(
    monkeypatch,
    caplog,
) -> None:
    response = FakeResponse()
    request: dict = {}

    def fake_get(url: str, **kwargs):
        request["url"] = url
        request.update(kwargs)
        return response

    monkeypatch.setattr(
        "pdi.adapters.immich.adapter.requests.get",
        fake_get,
    )

    adapter = ImmichAdapter(
        base_url="https://immich.example/",
        api_key="test-api-key",
    )

    with caplog.at_level(logging.INFO):
        adapter.connect()

    assert request == {
        "url": "https://immich.example/api/server/about",
        "headers": {
            "x-api-key": "test-api-key",
        },
        "timeout": 10,
    }
    assert response.raise_for_status_called is True
    assert "Connecting Immich..." in caplog.messages
    assert "Connected to Immich" in caplog.messages


def test_connect_does_not_swallow_http_errors(
    monkeypatch,
) -> None:
    class ErrorResponse(FakeResponse):
        def raise_for_status(self) -> None:
            raise requests.HTTPError(
                "Immich authentication failed"
            )

    monkeypatch.setattr(
        "pdi.adapters.immich.adapter.requests.get",
        lambda *args, **kwargs: ErrorResponse(),
    )

    adapter = ImmichAdapter(
        base_url="https://immich.example",
        api_key="invalid-api-key",
    )

    with pytest.raises(
        requests.HTTPError,
        match="Immich authentication failed",
    ):
        adapter.connect()


def test_scan_paginates_and_maps_provider_facts(
    monkeypatch,
    caplog,
) -> None:
    asset = {
        "id": "asset-1",
        "originalPath": "/library/photo.jpg",
        "originalFileName": "photo.jpg",
        "originalMimeType": "image/jpeg",
        "updatedAt": "2026-07-20T01:02:03.000Z",
        "checksum": "js0B4cvgxvZPg1MYAQygR6r8vQc=",
        "width": 4032,
        "height": 3024,
        "duration": "0:00:00.00000",
        "isFavorite": True,
        "isArchived": False,
        "isTrashed": False,
        "visibility": "timeline",
        "isEdited": False,
        "ownerId": "excluded-owner",
        "libraryId": "excluded-library",
        "thumbhash": "excluded-thumbhash",
        "exifInfo": {
            "fileSizeInByte": 123456,
            "make": "Camera Co.",
            "model": "Camera Model",
        },
    }
    second_asset = {
        "id": "asset-2",
        "originalPath": "/library/video.mp4",
        "originalFileName": "video.mp4",
        "originalMimeType": "video/mp4",
        "updatedAt": "2026-07-20T02:03:04.000Z",
        "checksum": "second-checksum",
        "width": 1920,
        "height": 1080,
        "duration": "0:00:12.00000",
        "isFavorite": False,
        "isArchived": True,
        "isTrashed": False,
        "visibility": "archive",
        "isEdited": True,
        "exifInfo": {
            "fileSizeInByte": 654321,
        },
    }
    responses = [
        FakeResponse(
            json_data={
                "assets": {
                    "items": [asset],
                    "nextPage": "2",
                    "count": 1,
                    "total": 2,
                },
            },
        ),
        FakeResponse(
            json_data={
                "assets": {
                    "items": [second_asset],
                    "nextPage": None,
                    "count": 1,
                    "total": 2,
                },
            },
        ),
    ]
    requests: list[dict] = []

    def fake_post(url: str, **kwargs):
        requests.append(
            {
                "url": url,
                **kwargs,
            }
        )
        return responses[len(requests) - 1]

    monkeypatch.setattr(
        "pdi.adapters.immich.adapter.requests.post",
        fake_post,
    )

    adapter = ImmichAdapter(
        base_url="https://immich.example",
        api_key="test-api-key",
    )

    with caplog.at_level(logging.INFO):
        facts = list(adapter.scan())

    assert len(facts) == 2
    assert requests == [
        {
            "url": "https://immich.example/api/search/metadata",
            "headers": {
                "x-api-key": "test-api-key",
            },
            "json": {
                "page": 1,
                "size": 1000,
                "withExif": True,
            },
            "timeout": 30,
        },
        {
            "url": "https://immich.example/api/search/metadata",
            "headers": {
                "x-api-key": "test-api-key",
            },
            "json": {
                "page": 2,
                "size": 1000,
                "withExif": True,
            },
            "timeout": 30,
        },
    ]
    assert all(
        response.raise_for_status_called
        for response in responses
    )

    fact = facts[0]

    assert fact.provider == "immich"
    assert fact.kind == "file"
    assert fact.external_id == "asset-1"
    assert fact.name == "photo.jpg"
    assert fact.attributes == {
        "path": "/library/photo.jpg",
        "size": 123456,
        "mime_type": "image/jpeg",
        "version_tag": "2026-07-20T01:02:03.000Z",
        "content_hash": None,
    }
    assert fact.raw == {
        "checksum": "js0B4cvgxvZPg1MYAQygR6r8vQc=",
        "checksum_algorithm": "sha1",
        "checksum_encoding": "base64",
        "width": 4032,
        "height": 3024,
        "exif": {
            "fileSizeInByte": 123456,
            "make": "Camera Co.",
            "model": "Camera Model",
        },
        "favorite": True,
        "archived": False,
        "trashed": False,
        "visibility": "timeline",
        "duration": "0:00:00.00000",
        "isEdited": False,
    }
    assert "ownerId" not in fact.raw
    assert "libraryId" not in fact.raw
    assert "thumbhash" not in fact.raw
    assert "Scanning Immich..." in caplog.messages
    assert "Found 2 Immich assets" in caplog.messages
    assert "Immich scan finished" in caplog.messages


@pytest.mark.parametrize(
    ("file_size", "expected_size"),
    [
        (123456, 123456),
        ("123456", 123456),
        (None, None),
        ("", None),
        ("abc", None),
        (True, None),
        (False, None),
        (-1, None),
    ],
)
def test_maps_only_valid_file_sizes(
    file_size,
    expected_size,
) -> None:
    fact = ImmichAdapter._to_provider_fact(
        {
            "id": "asset-1",
            "exifInfo": {
                "fileSizeInByte": file_size,
            },
        }
    )

    assert fact.attributes["size"] == expected_size


@pytest.mark.parametrize(
    "external_id",
    [
        None,
        "",
    ],
)
def test_rejects_invalid_external_id(
    external_id,
) -> None:
    with pytest.raises(
        ValueError,
        match="Immich asset does not contain a valid id",
    ):
        ImmichAdapter._to_provider_fact(
            {
                "id": external_id,
            }
        )


def test_open_streams_original_asset(
    monkeypatch,
) -> None:
    response = FakeResponse(
        chunks=(
            b"first",
            b"",
            b"second",
        ),
    )
    request: dict = {}

    def fake_get(url: str, **kwargs):
        request["url"] = url
        request.update(kwargs)
        return response

    monkeypatch.setattr(
        "pdi.adapters.immich.adapter.requests.get",
        fake_get,
    )

    adapter = ImmichAdapter(
        base_url="https://immich.example",
        api_key="test-api-key",
    )
    fact = ProviderFact(
        provider="immich",
        kind="file",
        external_id="asset/id",
        name="photo.jpg",
        attributes={},
        raw={},
    )

    assert list(adapter.open(fact)) == [
        b"first",
        b"second",
    ]
    assert request == {
        "url": (
            "https://immich.example"
            "/api/assets/asset%2Fid/original"
        ),
        "headers": {
            "x-api-key": "test-api-key",
        },
        "stream": True,
        "timeout": 30,
    }
    assert response.raise_for_status_called is True
    assert response.closed is True
