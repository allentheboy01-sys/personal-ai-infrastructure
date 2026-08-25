"""Production entry point for the credential-owning Web access service."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from .http import PinnedHttpClient
from .ipc import serve_systemd
from .providers import TavilySearchProvider
from .service import WebAccessService


CREDENTIAL_NAME = "tavily-api-key"


def _read_credential() -> str:
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if not directory:
        raise RuntimeError("search credential unavailable")
    path = Path(directory) / CREDENTIAL_NAME
    value = path.read_text(encoding="utf-8").strip()
    if not value or len(value) > 512 or not value.isascii() or any(char.isspace() for char in value):
        raise RuntimeError("search credential unavailable")
    return value


def main() -> None:
    client = PinnedHttpClient()
    provider = TavilySearchProvider(_read_credential(), client)
    asyncio.run(serve_systemd(WebAccessService(provider, client=client)))


if __name__ == "__main__":
    main()
