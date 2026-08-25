"""Narrow search-provider abstraction and Tavily Basic Search adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

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
