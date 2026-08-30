from collections.abc import AsyncIterator
import urllib.parse

import httpx

from .errors import ProviderInvalidResponseError, ProviderUnavailableError
from .text_provider import ProviderTextContent


TEXT_CHUNK_SIZE = 64 * 1024


class NextcloudTextAdapter:
    """Authenticated, read-only WebDAV access to one resolved Provider path."""

    provider = "nextcloud"

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._client = client

    async def open_text(
        self,
        provider_locator: str,
    ) -> ProviderTextContent:
        path = self._safe_provider_path(provider_locator)
        username = urllib.parse.quote(self._username, safe="")
        encoded_path = urllib.parse.quote(path, safe="/")
        url = (
            f"{self._base_url}/remote.php/dav/files/"
            f"{username}/{encoded_path}"
        )
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            follow_redirects=False,
            limits=httpx.Limits(
                max_connections=8,
                max_keepalive_connections=8,
            ),
            timeout=httpx.Timeout(
                connect=3.0,
                read=30.0,
                write=5.0,
                pool=3.0,
            ),
        )

        try:
            request = client.build_request(
                "GET",
                url,
                headers={"accept-encoding": "identity"},
            )
            response = await client.send(
                request,
                stream=True,
                auth=httpx.BasicAuth(self._username, self._password),
                follow_redirects=False,
            )
        except (httpx.TimeoutException, httpx.RequestError):
            if owns_client:
                await client.aclose()
            raise ProviderUnavailableError(
                "Nextcloud text service is unavailable"
            ) from None
        except (TypeError, ValueError):
            if owns_client:
                await client.aclose()
            raise ProviderInvalidResponseError(
                "Nextcloud text Source is invalid"
            ) from None

        async def body() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_raw(
                    chunk_size=TEXT_CHUNK_SIZE,
                ):
                    if chunk:
                        yield chunk
            except (httpx.TimeoutException, httpx.RequestError):
                raise ProviderUnavailableError(
                    "Nextcloud text stream is unavailable"
                ) from None

        closed = False

        async def close() -> None:
            nonlocal closed
            if closed:
                return
            closed = True
            try:
                await response.aclose()
            finally:
                if owns_client:
                    await client.aclose()

        return ProviderTextContent(
            status_code=response.status_code,
            media_type=response.headers.get("content-type"),
            content_length=response.headers.get("content-length"),
            body=body(),
            close=close,
            content_encoding=response.headers.get("content-encoding"),
        )

    @staticmethod
    def _safe_provider_path(value: str) -> str:
        if not isinstance(value, str):
            raise ProviderInvalidResponseError(
                "Nextcloud text Source is invalid"
            )
        path = value.strip("/")
        if (
            not path
            or "\\" in path
            or urllib.parse.urlsplit(path).scheme
            or any(ord(character) < 32 for character in path)
            or any(part in {"", ".", ".."} for part in path.split("/"))
        ):
            raise ProviderInvalidResponseError(
                "Nextcloud text Source is invalid"
            )
        return path
