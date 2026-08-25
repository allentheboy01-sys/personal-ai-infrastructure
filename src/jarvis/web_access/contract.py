"""Frozen Web/Search V0.1 limits and sanitized failure contract."""

from __future__ import annotations

from dataclasses import dataclass


WEB_SEARCH_TOOL = "jarvis_web_search"
WEB_FETCH_TOOL = "jarvis_web_fetch"

MAX_QUERY_CHARS = 400
MAX_URL_CHARS = 2_048
MAX_SEARCH_RESULTS = 5
MAX_REDIRECTS = 3
MAX_RAW_BODY_BYTES = 2 * 1024 * 1024
MAX_EXTRACTED_TEXT_CHARS = 20_000
MAX_TOOL_RESULT_CHARS = 24_000
MAX_IPC_REQUEST_BYTES = 8 * 1024
MAX_IPC_RESPONSE_BYTES = 96 * 1024
MAX_HEADER_BYTES = 64 * 1024
MAX_HEADER_COUNT = 100

DNS_TIMEOUT_SECONDS = 2.0
CONNECT_TIMEOUT_SECONDS = 5.0
FIRST_BYTE_TIMEOUT_SECONDS = 8.0
READ_IDLE_TIMEOUT_SECONDS = 5.0
FETCH_TIMEOUT_SECONDS = 15.0
SEARCH_TIMEOUT_SECONDS = 12.0

ALLOWED_FETCH_MIMES = frozenset(
    {
        "text/html",
        "text/plain",
        "text/markdown",
        "application/xhtml+xml",
        "application/json",
    }
)


@dataclass(frozen=True, slots=True)
class WebAccessError(Exception):
    """One stable public error code; private causes are deliberately omitted."""

    code: str

    def __str__(self) -> str:
        return self.code


def failure(code: str) -> dict[str, object]:
    return {"ok": False, "error": code}
