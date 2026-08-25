"""Narrow, deployment-selected search-provider adapters."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlsplit

from ddgs import DDGS
from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException as DDGSTimeoutException

from .contract import MAX_SEARCH_RESULTS, SEARCH_TIMEOUT_SECONDS, WebAccessError
from .http import PinnedHttpClient


@dataclass(frozen=True, slots=True)
class ProviderSearchResult:
    title: str
    url: str
    snippet: str
    published_at: str | None = None


class SearchProvider(Protocol):
    async def search(self, query: str, limit: int) -> tuple[ProviderSearchResult, ...]: ...


class _DDGSClient(Protocol):
    def text(self, query: str, **kwargs: Any) -> list[dict[str, Any]]: ...


_DDGSFactory = Callable[..., _DDGSClient]
_DUCKDUCKGO_WRAPPER_HOSTS = frozenset({"duckduckgo.com", "www.duckduckgo.com"})
_DUCKDUCKGO_WRAPPER_PATHS = frozenset({"/l", "/l/"})
_DUCKDUCKGO_WRAPPER_KEYS = frozenset({"uddg", "rut"})
_DDGS_TIMEOUT_SECONDS = 5
_DDGS_REGIONS = frozenset({"wt-wt", "cn-zh", "us-en"})
_DDGS_BACKENDS = frozenset({"brave", "duckduckgo", "mojeek", "yahoo"})
DDGS_PROXY_ENDPOINT = "socks5://127.0.0.1:10808"


def _normalize_ddgs_result_url(raw_url: str) -> str | None:
    """Unwrap only the one recognized DDG redirect shape.

    Public-destination validation remains the responsibility of
    ``WebAccessService``. Unknown DDG tracking shapes are dropped rather than
    becoming citation URLs.
    """

    if not raw_url or len(raw_url) > 2_048:
        return None
    candidate = f"https:{raw_url}" if raw_url.startswith("//") else raw_url
    try:
        split = urlsplit(candidate)
        hostname = (split.hostname or "").rstrip(".").lower()
        port = split.port
    except (ValueError, UnicodeError):
        return None
    if hostname not in _DUCKDUCKGO_WRAPPER_HOSTS:
        return raw_url
    looks_like_wrapper = split.path in _DUCKDUCKGO_WRAPPER_PATHS or split.path.startswith("/l/") or "uddg=" in split.query
    if not looks_like_wrapper:
        return raw_url
    if split.scheme != "https" or port not in {None, 443} or split.path not in _DUCKDUCKGO_WRAPPER_PATHS:
        return None
    try:
        pairs = parse_qsl(split.query, keep_blank_values=True, max_num_fields=4)
    except (ValueError, UnicodeError):
        return None
    if any(key not in _DUCKDUCKGO_WRAPPER_KEYS for key, _value in pairs):
        return None
    targets = [value for key, value in pairs if key == "uddg"]
    if len(targets) != 1 or not targets[0] or len(targets[0]) > 2_048:
        return None
    return targets[0]


class DDGSSearchProvider:
    """Keyless DDGS text search through one deployment-selected backend.

    Cancelling an async waiter cannot kill an already-running Python thread.
    The semaphore is therefore released only when that worker actually exits,
    preventing a cancelled request from creating overlapping DDGS searches.
    """

    def __init__(
        self,
        *,
        region: str,
        backend: str,
        proxy: str,
        timeout: int = _DDGS_TIMEOUT_SECONDS,
        factory: _DDGSFactory = DDGS,
    ) -> None:
        if region not in _DDGS_REGIONS:
            raise ValueError("unsupported DDGS region")
        if backend not in _DDGS_BACKENDS:
            raise ValueError("unsupported DDGS backend")
        if proxy != DDGS_PROXY_ENDPOINT:
            raise ValueError("unsupported DDGS proxy")
        if not 1 <= timeout <= _DDGS_TIMEOUT_SECONDS:
            raise ValueError("invalid DDGS timeout")
        self._region = region
        self._backend = backend
        self._proxy = proxy
        self._timeout = timeout
        self._factory = factory
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jarvis-ddgs")
        self._gate = asyncio.Semaphore(1)

    def _search_sync(self, query: str, limit: int) -> tuple[ProviderSearchResult, ...]:
        try:
            client = self._factory(proxy=self._proxy, timeout=self._timeout, verify=True)
            rows = client.text(
                query,
                region=self._region,
                safesearch="moderate",
                timelimit=None,
                max_results=limit,
                page=1,
                backend=self._backend,
            )
        except RatelimitException:
            raise WebAccessError("provider_quota") from None
        except DDGSTimeoutException:
            raise WebAccessError("provider_timeout") from None
        except DDGSException:
            raise WebAccessError("provider_unavailable") from None
        except Exception:
            raise WebAccessError("provider_unavailable") from None
        if not isinstance(rows, list):
            raise WebAccessError("provider_unavailable")
        results: list[ProviderSearchResult] = []
        for row in rows[: min(limit, MAX_SEARCH_RESULTS)]:
            if not isinstance(row, dict):
                continue
            title, raw_url, snippet = row.get("title"), row.get("href"), row.get("body")
            if not all(isinstance(value, str) for value in (title, raw_url, snippet)):
                continue
            url = _normalize_ddgs_result_url(raw_url)
            if url is None:
                continue
            results.append(ProviderSearchResult(title[:512], url, snippet[:2_000], None))
        return tuple(results)

    async def search(self, query: str, limit: int) -> tuple[ProviderSearchResult, ...]:
        await self._gate.acquire()
        try:
            future = asyncio.get_running_loop().run_in_executor(self._executor, self._search_sync, query, limit)
        except BaseException:
            self._gate.release()
            raise

        def worker_done(done: asyncio.Future[tuple[ProviderSearchResult, ...]]) -> None:
            self._gate.release()
            if not done.cancelled():
                # Retrieve a background exception even when the async waiter was
                # cancelled, avoiding an unhandled-future diagnostic.
                done.exception()

        future.add_done_callback(worker_done)
        return await asyncio.shield(future)


class TavilySearchProvider:
    """Tavily stays replaceable and its response never crosses this adapter."""

    ENDPOINT = "https://api.tavily.com/search"

    def __init__(self, api_key: str, client: PinnedHttpClient | None = None) -> None:
        if not api_key or len(api_key) > 512 or not api_key.isascii() or any(char.isspace() for char in api_key):
            raise ValueError("search credential unavailable")
        self._api_key = api_key
        self._client = client or PinnedHttpClient()

    async def search(self, query: str, limit: int) -> tuple[ProviderSearchResult, ...]:
        payload = json.dumps(
            {
                "query": query,
                "search_depth": "basic",
                "max_results": min(limit, MAX_SEARCH_RESULTS),
                "include_answer": False,
                "include_raw_content": False,
                "include_images": False,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            response = await self._client.request(
                "POST",
                self.ENDPOINT,
                headers={
                    "authorization": f"Bearer {self._api_key}",
                    "content-type": "application/json",
                    "accept": "application/json",
                },
                body=payload,
                overall_timeout=SEARCH_TIMEOUT_SECONDS,
            )
        except WebAccessError as error:
            if error.code == "http_429":
                raise WebAccessError("provider_quota") from None
            if error.code == "timeout":
                raise WebAccessError("provider_timeout") from None
            raise WebAccessError("provider_unavailable") from None
        if response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise WebAccessError("provider_unavailable")
        try:
            raw = json.loads(response.body)
        except (json.JSONDecodeError, UnicodeError, RecursionError):
            raise WebAccessError("provider_unavailable") from None
        rows = raw.get("results") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            raise WebAccessError("provider_unavailable")
        results: list[ProviderSearchResult] = []
        for row in rows[:MAX_SEARCH_RESULTS]:
            if not isinstance(row, dict):
                continue
            title, url, snippet = row.get("title"), row.get("url"), row.get("content")
            published_at = row.get("published_date")
            if not all(isinstance(value, str) for value in (title, url, snippet)):
                continue
            if published_at is not None and not isinstance(published_at, str):
                published_at = None
            results.append(
                ProviderSearchResult(
                    title=title[:512],
                    url=url[:2_048],
                    snippet=snippet[:2_000],
                    published_at=published_at[:64] if published_at else None,
                )
            )
        return tuple(results[:limit])
