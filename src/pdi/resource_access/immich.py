from collections.abc import AsyncIterator
from uuid import UUID

import httpx

from .errors import (
    ProviderInvalidResponseError,
    ProviderUnavailableError,
)
from .models import ResourceRepresentationKind
from .provider import ProviderRepresentation


CHUNK_SIZE = 64 * 1024


class ImmichRepresentationAdapter:
    provider = "immich"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
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

    async def open_representation(
        self,
        provider_locator: str,
        representation_kind: ResourceRepresentationKind,
    ) -> ProviderRepresentation:
        try:
            locator = UUID(provider_locator)
        except (TypeError, ValueError, AttributeError) as error:
            raise ProviderInvalidResponseError(
                "Provider Source has an invalid locator"
            ) from None

        if str(locator) != provider_locator:
            raise ProviderInvalidResponseError(
                "Provider Source has an invalid locator"
            )

        request = self._client.build_request(
            "GET",
            f"{self._base_url}/api/assets/{locator}/thumbnail",
            headers={"x-api-key": self._api_key},
            params={"size": representation_kind.value},
        )

        try:
            response = await self._client.send(request, stream=True)
        except (httpx.TimeoutException, httpx.RequestError) as error:
            raise ProviderUnavailableError(
                "Immich representation service is unavailable"
            ) from None

        async def body() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_raw(
                    chunk_size=CHUNK_SIZE,
                ):
                    if chunk:
                        yield chunk
            except (httpx.TimeoutException, httpx.RequestError) as error:
                raise ProviderUnavailableError(
                    "Immich representation stream is unavailable"
                ) from None

        return ProviderRepresentation(
            status_code=response.status_code,
            media_type=response.headers.get("content-type"),
            content_length=response.headers.get("content-length"),
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            body=body(),
            close=response.aclose,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
