import asyncio
import json
from dataclasses import dataclass

import pytest

from jarvis.web_access.contract import MAX_TOOL_RESULT_CHARS, WebAccessError
from jarvis.web_access.http import HttpResponse
from jarvis.web_access.providers import ProviderSearchResult, TavilySearchProvider
from jarvis.web_access.security import PublicResolver
from jarvis.web_access.service import WebAccessService


class FakeProvider:
    def __init__(self, rows=(), error: WebAccessError | None = None) -> None:
        self.rows = tuple(rows)
        self.error = error
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, limit: int):
        self.calls.append((query, limit))
        if self.error:
            raise self.error
        return self.rows


class FakeHttpClient:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.urls: list[str] = []

    async def get(self, url: str) -> HttpResponse:
        self.urls.append(url)
        return self.response


def test_search_returns_only_bounded_canonical_public_contract() -> None:
    rows = [
        ProviderSearchResult(" One ", "https://8.8.8.8/a#fragment", " snippet ", "2026-01-02"),
        ProviderSearchResult("Blocked", "http://127.0.0.1/private", "never"),
    ]
    service = WebAccessService(FakeProvider(rows), resolver=PublicResolver())
    result = asyncio.run(service.search("  current info  ", 5))
    assert result == {
        "ok": True,
        "results": [
            {
                "rank": 1,
                "title": "One",
                "url": "https://8.8.8.8/a",
                "snippet": "snippet",
                "published_at": "2026-01-02",
                "retrieved_at": result["results"][0]["retrieved_at"],  # type: ignore[index]
            }
        ],
        "truncated": False,
    }
    assert "provider" not in json.dumps(result)


@pytest.mark.parametrize("query,limit", [("", 5), (" " * 2, 5), ("x" * 401, 5), ("x", 0), ("x", 6), ("x", True)])
def test_search_input_bounds(query, limit) -> None:
    result = asyncio.run(WebAccessService(FakeProvider()).search(query, limit))
    assert result == {"ok": False, "error": "invalid_request"}


@pytest.mark.parametrize(
    "content_type,expected",
    [
        ("text/html; charset=utf-8", True),
        ("text/plain", True),
        ("text/markdown", True),
        ("application/xhtml+xml", True),
        ("application/json", True),
        ("application/pdf", False),
        ("video/mp4", False),
        ("audio/mpeg", False),
        ("application/octet-stream", False),
    ],
)
def test_fetch_mime_allowlist(content_type: str, expected: bool) -> None:
    response = HttpResponse(200, {"content-type": content_type}, b"<p>hello</p>", "https://8.8.8.8/final")
    service = WebAccessService(FakeProvider(), client=FakeHttpClient(response))  # type: ignore[arg-type]
    result = asyncio.run(service.fetch("https://8.8.8.8/start"))
    assert result["ok"] is expected
    assert result.get("error") == (None if expected else "unsupported_mime")
    if expected:
        assert result["content_trust"] == "untrusted_web"
        assert result["requested_url"] == "https://8.8.8.8/start"
        assert result["final_url"] == "https://8.8.8.8/final"
        assert len(json.dumps(result, ensure_ascii=False, separators=(",", ":"))) <= MAX_TOOL_RESULT_CHARS


class RecordingProviderHttp:
    def __init__(self, response: HttpResponse | None = None, error: WebAccessError | None = None) -> None:
        self.response = response
        self.error = error
        self.calls = []

    async def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self.response


def test_tavily_adapter_uses_basic_bounded_request_and_sanitizes_response() -> None:
    raw = {
        "answer": "must not escape",
        "request_id": "private-debug",
        "results": [
            {"title": "Title", "url": "https://example.com/", "content": "Snippet", "score": 0.9, "raw_content": "private"}
        ],
    }
    response = HttpResponse(200, {"content-type": "application/json"}, json.dumps(raw).encode(), TavilySearchProvider.ENDPOINT)
    http = RecordingProviderHttp(response)
    provider = TavilySearchProvider("tvly-test", http)  # type: ignore[arg-type]
    result = asyncio.run(provider.search("query", 3))
    assert result == (ProviderSearchResult("Title", "https://example.com/", "Snippet", None),)
    args, kwargs = http.calls[0]
    assert args == ("POST", TavilySearchProvider.ENDPOINT)
    assert kwargs["headers"]["authorization"] == "Bearer tvly-test"
    body = json.loads(kwargs["body"])
    assert body == {
        "query": "query",
        "search_depth": "basic",
        "max_results": 3,
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
    }
    assert "private-debug" not in repr(result) and "raw_content" not in repr(result)


@pytest.mark.parametrize(
    "upstream,expected",
    [("http_429", "provider_quota"), ("timeout", "provider_timeout"), ("http_403", "provider_unavailable")],
)
def test_tavily_provider_failures_are_stable_and_sanitized(upstream: str, expected: str) -> None:
    provider = TavilySearchProvider("tvly-test", RecordingProviderHttp(error=WebAccessError(upstream)))  # type: ignore[arg-type]
    with pytest.raises(WebAccessError) as caught:
        asyncio.run(provider.search("query", 5))
    assert caught.value.code == expected


def test_global_outbound_limit_is_four() -> None:
    @dataclass
    class BlockingProvider:
        active: int = 0
        maximum: int = 0

        async def search(self, query: str, limit: int):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            await asyncio.sleep(0.02)
            self.active -= 1
            return ()

    async def run() -> int:
        provider = BlockingProvider()
        service = WebAccessService(provider)
        await asyncio.gather(*(service.search(f"q{index}", 1) for index in range(8)))
        return provider.maximum

    assert asyncio.run(run()) == 4
