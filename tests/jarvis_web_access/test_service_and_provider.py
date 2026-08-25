import asyncio
import json
import threading
import time
from dataclasses import dataclass

import pytest
from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException as DDGSTimeoutException

from jarvis.web_access.contract import MAX_TOOL_RESULT_CHARS, WebAccessError
from jarvis.web_access.http import HttpResponse
from jarvis.web_access.providers import DDGS_PROXY_ENDPOINT, DDGSSearchProvider, ProviderSearchResult, TavilySearchProvider
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


class RecordingDDGSFactory:
    def __init__(self, rows=(), error: Exception | None = None, delay: float = 0.0) -> None:
        self.rows = list(rows)
        self.error = error
        self.delay = delay
        self.instances: list[dict[str, object]] = []
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.worker_threads: list[int] = []
        self.active = 0
        self.maximum = 0
        self._lock = threading.Lock()

    def __call__(self, **kwargs):
        self.instances.append(kwargs)
        owner = self

        class Client:
            def text(self, query: str, **options):
                with owner._lock:
                    owner.active += 1
                    owner.maximum = max(owner.maximum, owner.active)
                try:
                    owner.worker_threads.append(threading.get_ident())
                    owner.calls.append((query, options))
                    if owner.delay:
                        time.sleep(owner.delay)
                    if owner.error:
                        raise owner.error
                    return list(owner.rows)
                finally:
                    with owner._lock:
                        owner.active -= 1

        return Client()


def test_ddgs_adapter_uses_one_bounded_deployment_backend_text_call_off_event_loop() -> None:
    factory = RecordingDDGSFactory(
        [
            {"title": " One ", "href": "https://8.8.8.8/a#fragment", "body": " snippet ", "date": "ignored"},
            {"title": "Two", "href": "https://1.1.1.1/b", "body": "second"},
        ]
    )
    provider = DDGSSearchProvider(region="cn-zh", backend="brave", proxy=DDGS_PROXY_ENDPOINT, factory=factory)
    event_loop_thread = threading.get_ident()
    result = asyncio.run(provider.search("公开查询", 1))
    assert result == (ProviderSearchResult(" One ", "https://8.8.8.8/a#fragment", " snippet ", None),)
    assert factory.instances == [{"proxy": DDGS_PROXY_ENDPOINT, "timeout": 5, "verify": True}]
    assert factory.calls == [
        (
            "公开查询",
            {
                "region": "cn-zh",
                "safesearch": "moderate",
                "timelimit": None,
                "max_results": 1,
                "page": 1,
                "backend": "brave",
            },
        )
    ]
    assert factory.worker_threads != [event_loop_thread]


def test_ddgs_provider_serializes_workers_and_creates_one_instance_per_request() -> None:
    factory = RecordingDDGSFactory([], delay=0.03)
    provider = DDGSSearchProvider(region="wt-wt", backend="brave", proxy=DDGS_PROXY_ENDPOINT, factory=factory)

    async def run():
        return await asyncio.gather(provider.search("one", 5), provider.search("two", 5))

    assert asyncio.run(run()) == [(), ()]
    assert factory.maximum == 1
    assert len(factory.instances) == 2


def test_cancelled_ddgs_waiter_does_not_allow_an_overlapping_worker() -> None:
    factory = RecordingDDGSFactory([], delay=0.05)
    provider = DDGSSearchProvider(region="us-en", backend="brave", proxy=DDGS_PROXY_ENDPOINT, factory=factory)

    async def run() -> None:
        first = asyncio.create_task(provider.search("one", 5))
        await asyncio.sleep(0.01)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        await provider.search("two", 5)

    asyncio.run(run())
    assert factory.maximum == 1
    assert [query for query, _options in factory.calls] == ["one", "two"]


@pytest.mark.parametrize(
    "error,expected",
    [
        (RatelimitException("limited"), "provider_quota"),
        (DDGSTimeoutException("timed out"), "provider_timeout"),
        (DDGSException("challenge details"), "provider_unavailable"),
        (RuntimeError("private backend detail"), "provider_unavailable"),
    ],
)
def test_ddgs_provider_failures_are_stable_and_sanitized(error: Exception, expected: str) -> None:
    factory = RecordingDDGSFactory(error=error)
    provider = DDGSSearchProvider(
        region="wt-wt",
        backend="brave",
        proxy=DDGS_PROXY_ENDPOINT,
        factory=factory,
    )
    with pytest.raises(WebAccessError) as caught:
        asyncio.run(provider.search("query", 5))
    assert caught.value.code == expected
    assert "challenge" not in str(caught.value) and "private" not in str(caught.value)
    assert len(factory.instances) == 1
    assert len(factory.calls) == 1


def test_ddgs_tracking_wrapper_is_strict_and_target_still_uses_public_validation() -> None:
    rows = [
        {"title": "Direct", "href": "https://8.8.8.8/direct", "body": "ok"},
        {
            "title": "Wrapped",
            "href": "//duckduckgo.com/l/?uddg=https%3A%2F%2F1.1.1.1%2Fsource&rut=opaque",
            "body": "ok",
        },
        {
            "title": "Private",
            "href": "https://duckduckgo.com/l/?uddg=http%3A%2F%2F127.0.0.1%2Fprivate",
            "body": "drop",
        },
        {"title": "Malformed", "href": "https://duckduckgo.com/l/?rut=missing", "body": "drop"},
        {"title": "Unknown", "href": "https://duckduckgo.com/redirect?uddg=https%3A%2F%2F8.8.4.4", "body": "drop"},
    ]
    provider = DDGSSearchProvider(
        region="wt-wt", backend="brave", proxy=DDGS_PROXY_ENDPOINT, factory=RecordingDDGSFactory(rows)
    )
    service = WebAccessService(provider, resolver=PublicResolver())
    result = asyncio.run(service.search("query", 5))
    assert result["ok"] is True
    assert [row["url"] for row in result["results"]] == ["https://8.8.8.8/direct", "https://1.1.1.1/source"]


@pytest.mark.parametrize("region", ["", "zh", "auto", "cn-ZH"])
def test_ddgs_region_is_a_bounded_deployment_value(region: str) -> None:
    with pytest.raises(ValueError, match="unsupported DDGS region"):
        DDGSSearchProvider(region=region, backend="brave", proxy=DDGS_PROXY_ENDPOINT)


@pytest.mark.parametrize("backend", ["", "auto", "all", "bing", "brave,yahoo", "BRAVE"])
def test_ddgs_backend_is_one_bounded_deployment_value(backend: str) -> None:
    with pytest.raises(ValueError, match="unsupported DDGS backend"):
        DDGSSearchProvider(region="wt-wt", backend=backend, proxy=DDGS_PROXY_ENDPOINT)


@pytest.mark.parametrize("backend", ["brave", "duckduckgo", "mojeek", "yahoo"])
def test_ddgs_backend_accepts_only_installed_single_text_engines(backend: str) -> None:
    DDGSSearchProvider(region="wt-wt", backend=backend, proxy=DDGS_PROXY_ENDPOINT)


@pytest.mark.parametrize(
    "proxy",
    [
        "",
        "socks5://127.0.0.1:10809",
        "http://127.0.0.1:10808",
        "socks5://192.168.1.1:10808",
        "socks5://example.com:10808",
    ],
)
def test_ddgs_proxy_is_the_one_reviewed_provider_endpoint(proxy: str) -> None:
    with pytest.raises(ValueError, match="unsupported DDGS proxy"):
        DDGSSearchProvider(region="wt-wt", backend="brave", proxy=proxy)


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
