import xml.etree.ElementTree as ET
from collections import Counter

import pytest
import requests

from pdi.adapters.base import ProviderFact
from pdi.adapters.nextcloud.adapter import NextcloudAdapter


DAV_ROOT = "/remote.php/dav/files/test-user/"


class FakeResponse:
    def __init__(
        self,
        text: str,
        *,
        error: Exception | None = None,
    ) -> None:
        self.text = text
        self.error = error
        self.raise_for_status_called = False

    def raise_for_status(self) -> None:
        self.raise_for_status_called = True

        if self.error is not None:
            raise self.error


def _webdav_response(
    *,
    path: str,
    external_id: str,
    collection: bool = False,
) -> str:
    normalized_path = path.strip("/")
    href = f"{DAV_ROOT}{normalized_path}"

    if collection or not normalized_path:
        href += "/" if normalized_path else ""

    resource_type = (
        "<d:resourcetype><d:collection /></d:resourcetype>"
        if collection
        else "<d:resourcetype />"
    )

    return f"""
    <d:response>
      <d:href>{href}</d:href>
      <d:propstat>
        <d:prop>
          <oc:id>{external_id}</oc:id>
          <oc:fileid>{external_id}-fileid</oc:fileid>
          <d:getcontentlength>10</d:getcontentlength>
          <d:getcontenttype>text/plain</d:getcontenttype>
          <d:getetag>etag-{external_id}</d:getetag>
          <d:getlastmodified>Sun, 10 Aug 2026 00:00:00 GMT</d:getlastmodified>
          {resource_type}
        </d:prop>
      </d:propstat>
    </d:response>
    """


def _multistatus(*responses: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<d:multistatus xmlns:d="DAV:" '
        'xmlns:oc="http://owncloud.org/ns">'
        + "".join(responses)
        + "</d:multistatus>"
    )


def _adapter() -> NextcloudAdapter:
    return NextcloudAdapter(
        base_url="https://nextcloud.example",
        username="test-user",
        password="test-password",
    )


def test_scan_discovers_complete_tree_with_stable_external_ids(
    monkeypatch,
) -> None:
    responses = {
        "": _multistatus(
            _webdav_response(
                path="",
                external_id="root-self",
                collection=True,
            ),
            _webdav_response(
                path="root.md",
                external_id="root-file-id",
            ),
            _webdav_response(
                path="A",
                external_id="folder-a-id",
                collection=True,
            ),
            _webdav_response(
                path="Sibling",
                external_id="folder-sibling-id",
                collection=True,
            ),
        ),
        "A": _multistatus(
            _webdav_response(
                path="A/",
                external_id="folder-a-id",
                collection=True,
            ),
            _webdav_response(
                path="A/level1.md",
                external_id="level1-file-id",
            ),
            _webdav_response(
                path="A/B",
                external_id="folder-b-id",
                collection=True,
            ),
        ),
        "Sibling": _multistatus(
            _webdav_response(
                path="Sibling/",
                external_id="folder-sibling-id",
                collection=True,
            ),
            _webdav_response(
                path="Sibling/sibling.md",
                external_id="sibling-file-id",
            ),
        ),
        "A/B": _multistatus(
            _webdav_response(
                path="/A/B/",
                external_id="folder-b-id",
                collection=True,
            ),
            _webdav_response(
                path="A/B/level2.md",
                external_id="level2-file-id",
            ),
        ),
    }
    requested_paths: list[str] = []
    fake_responses: list[FakeResponse] = []

    def fake_request(*, method: str, url: str, **kwargs):
        assert method == "PROPFIND"
        assert kwargs["headers"]["Depth"] == "1"
        relative_path = url.removeprefix(
            "https://nextcloud.example" + DAV_ROOT
        ).strip("/")
        requested_paths.append(relative_path)
        response = FakeResponse(responses[relative_path])
        fake_responses.append(response)
        return response

    monkeypatch.setattr(
        "pdi.adapters.nextcloud.adapter.requests.request",
        fake_request,
    )

    facts = list(_adapter().scan())

    assert requested_paths == [
        "",
        "A",
        "Sibling",
        "A/B",
    ]
    assert all(
        response.raise_for_status_called
        for response in fake_responses
    )
    assert [fact.attributes["path"] for fact in facts] == [
        "root.md",
        "A/",
        "Sibling/",
        "A/level1.md",
        "A/B/",
        "Sibling/sibling.md",
        "A/B/level2.md",
    ]
    assert {
        fact.attributes["path"]: fact.external_id
        for fact in facts
    }["A/B/level2.md"] == "level2-file-id"
    assert "root-self" not in {
        fact.external_id
        for fact in facts
    }
    assert Counter(requested_paths) == {
        "": 1,
        "A": 1,
        "Sibling": 1,
        "A/B": 1,
    }
    assert all(
        fact.raw["getlastmodified"]
        == "Sun, 10 Aug 2026 00:00:00 GMT"
        for fact in facts
    )
    assert all("creationdate" not in fact.raw for fact in facts)


def test_scan_visits_a_repeated_directory_path_only_once(
    monkeypatch,
) -> None:
    adapter = _adapter()
    folder = ProviderFact(
        provider="nextcloud",
        kind="folder",
        external_id="folder-a-id",
        name="A",
        attributes={"path": "A/"},
        raw={},
    )
    calls: list[str] = []

    def fake_propfind(path: str) -> list[ProviderFact]:
        calls.append(path)
        return [folder, folder] if path == "" else []

    monkeypatch.setattr(adapter, "_propfind", fake_propfind)

    list(adapter.scan())

    assert calls == ["", "A"]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("", ""),
        ("/", ""),
        ("/A/", "A"),
        ("/A Folder/", "A Folder"),
    ],
)
def test_traversal_path_normalization(
    path: str,
    expected: str,
) -> None:
    assert (
        NextcloudAdapter._normalize_traversal_path(path)
        == expected
    )


def test_scan_propagates_malformed_nested_response(
    monkeypatch,
) -> None:
    responses = {
        "": _multistatus(
            _webdav_response(
                path="",
                external_id="root-self",
                collection=True,
            ),
            _webdav_response(
                path="A",
                external_id="folder-a-id",
                collection=True,
            ),
        ),
        "A": "<not-valid-webdav",
    }

    def fake_request(*, url: str, **kwargs):
        relative_path = url.removeprefix(
            "https://nextcloud.example" + DAV_ROOT
        ).strip("/")
        return FakeResponse(responses[relative_path])

    monkeypatch.setattr(
        "pdi.adapters.nextcloud.adapter.requests.request",
        fake_request,
    )

    with pytest.raises(ET.ParseError):
        list(_adapter().scan())


def test_scan_propagates_nested_http_failure(
    monkeypatch,
) -> None:
    root_response = _multistatus(
        _webdav_response(
            path="",
            external_id="root-self",
            collection=True,
        ),
        _webdav_response(
            path="A",
            external_id="folder-a-id",
            collection=True,
        ),
    )

    def fake_request(*, url: str, **kwargs):
        relative_path = url.removeprefix(
            "https://nextcloud.example" + DAV_ROOT
        ).strip("/")

        if relative_path == "A":
            return FakeResponse(
                "",
                error=requests.HTTPError("nested directory failed"),
            )

        return FakeResponse(root_response)

    monkeypatch.setattr(
        "pdi.adapters.nextcloud.adapter.requests.request",
        fake_request,
    )

    with pytest.raises(
        requests.HTTPError,
        match="nested directory failed",
    ):
        list(_adapter().scan())
