"""Application service for bounded public-Web search and fetch."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from .contract import (
    ALLOWED_FETCH_MIMES,
    MAX_QUERY_CHARS,
    MAX_SEARCH_RESULTS,
    MAX_TOOL_RESULT_CHARS,
    MAX_URL_CHARS,
    SEARCH_TIMEOUT_SECONDS,
    WebAccessError,
    failure,
)
from .extraction import extract_readable
from .http import PinnedHttpClient
from .providers import SearchProvider
from .security import PublicResolver, parse_public_url


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _serialized_chars(value: dict[str, object]) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _bound_result(value: dict[str, object]) -> dict[str, object]:
    """Keep the complete structured result under the frozen character bound."""

    # MCP renders structured content as indented JSON as well as structuredContent.
    # Reserve deterministic formatting headroom so the actual model-facing text
    # remains below the 24k contract, not only our compact IPC encoding.
    target_chars = MAX_TOOL_RESULT_CHARS - 512
    if _serialized_chars(value) <= target_chars:
        return value
    bounded = dict(value)
    bounded["truncated"] = True
    if isinstance(bounded.get("content"), str):
        content = bounded["content"]
        overflow = _serialized_chars(bounded) - target_chars
        bounded["content"] = content[: max(0, len(content) - overflow - 16)]
    elif isinstance(bounded.get("results"), list):
        rows = [dict(row) for row in bounded["results"] if isinstance(row, dict)]
        for row in reversed(rows):
            snippet = row.get("snippet")
            if isinstance(snippet, str) and _serialized_chars({**bounded, "results": rows}) > target_chars:
                row["snippet"] = snippet[:256]
        while rows and _serialized_chars({**bounded, "results": rows}) > target_chars:
            rows.pop()
        bounded["results"] = rows
    if _serialized_chars(bounded) > target_chars:
        raise WebAccessError("body_too_large")
    return bounded


class WebAccessService:
    def __init__(
        self,
        search_provider: SearchProvider,
        *,
        client: PinnedHttpClient | None = None,
        resolver: PublicResolver | None = None,
        global_limit: int = 4,
    ) -> None:
        self._search_provider = search_provider
        self._resolver = resolver or PublicResolver()
        self._client = client or PinnedHttpClient(resolver=self._resolver)
        self._outbound = asyncio.Semaphore(global_limit)

    async def search(self, query: object, limit: object = 5) -> dict[str, object]:
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
            return failure("invalid_request")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_SEARCH_RESULTS:
            return failure("invalid_request")
        try:
            async with asyncio.timeout(SEARCH_TIMEOUT_SECONDS):
                async with self._outbound:
                    provider_rows = await self._search_provider.search(query.strip(), limit)
                    accepted: list[dict[str, object]] = []
                    for row in provider_rows:
                        try:
                            pinned = await self._resolver.parse_and_resolve(row.url)
                        except WebAccessError:
                            continue
                        accepted.append(
                            {
                                "rank": len(accepted) + 1,
                                "title": row.title.strip()[:512],
                                "url": pinned.parsed.url,
                                "snippet": row.snippet.strip()[:2_000],
                                "published_at": row.published_at,
                                "retrieved_at": _now(),
                            }
                        )
                        if len(accepted) == limit:
                            break
            return _bound_result({"ok": True, "results": accepted, "truncated": len(provider_rows) > limit})
        except TimeoutError:
            return failure("provider_timeout")
        except WebAccessError as error:
            return failure(error.code)
        except Exception:
            return failure("provider_unavailable")

    async def fetch(self, url: object) -> dict[str, object]:
        if not isinstance(url, str) or not 1 <= len(url) <= MAX_URL_CHARS:
            return failure("invalid_request")
        try:
            requested = parse_public_url(url).url
            async with self._outbound:
                response = await self._client.get(requested)
            content_type = response.headers.get("content-type", "")
            mime = content_type.split(";", 1)[0].strip().lower()
            if mime not in ALLOWED_FETCH_MIMES:
                raise WebAccessError("unsupported_mime")
            title, content, extraction_truncated = extract_readable(response.body, content_type)
            result = {
                "ok": True,
                "requested_url": requested,
                "final_url": response.final_url,
                "title": title,
                "mime": mime,
                "content": content,
                "retrieved_at": _now(),
                "truncated": extraction_truncated,
                "content_trust": "untrusted_web",
            }
            return _bound_result(result)
        except WebAccessError as error:
            return failure(error.code)
        except Exception:
            return failure("provider_unavailable")
