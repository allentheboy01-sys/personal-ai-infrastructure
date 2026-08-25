"""Production entry point for the credential-owning Web access service."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from .http import PinnedHttpClient
from .ipc import serve_systemd
from .providers import DDGSSearchProvider, SearchProvider, TavilySearchProvider
from .service import WebAccessService


CREDENTIAL_NAME = "tavily-api-key"
SEARCH_PROVIDER_ENV = "JARVIS_WEB_SEARCH_PROVIDER"
SEARCH_REGION_ENV = "JARVIS_WEB_SEARCH_REGION"
DEFAULT_SEARCH_PROVIDER = "ddgs"
DEFAULT_DDGS_REGION = "wt-wt"
PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "DDGS_PROXY",
)


def _read_credential() -> str:
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if not directory:
        raise RuntimeError("search credential unavailable")
    path = Path(directory) / CREDENTIAL_NAME
    value = path.read_text(encoding="utf-8").strip()
    if not value or len(value) > 512 or not value.isascii() or any(char.isspace() for char in value):
        raise RuntimeError("search credential unavailable")
    return value


def _sanitize_proxy_environment() -> None:
    for name in PROXY_ENV_NAMES:
        os.environ.pop(name, None)


def _build_search_provider(client: PinnedHttpClient) -> SearchProvider:
    provider = os.environ.get(SEARCH_PROVIDER_ENV, DEFAULT_SEARCH_PROVIDER).strip().lower()
    if provider == "ddgs":
        region = os.environ.get(SEARCH_REGION_ENV, DEFAULT_DDGS_REGION).strip().lower()
        return DDGSSearchProvider(region=region)
    if provider == "tavily":
        return TavilySearchProvider(_read_credential(), client)
    raise RuntimeError("unsupported search provider")


def main() -> None:
    _sanitize_proxy_environment()
    client = PinnedHttpClient()
    provider = _build_search_provider(client)
    asyncio.run(serve_systemd(WebAccessService(provider, client=client)))


if __name__ == "__main__":
    main()
