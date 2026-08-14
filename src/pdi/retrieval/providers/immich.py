from typing import Any

import requests

from pdi.retrieval.errors import (
    ProviderCapabilityUnavailableError,
    ProviderInvalidResponseError,
    ProviderUnavailableError,
)
from pdi.retrieval.models import ProviderRetrievalHit


class ImmichSemanticRetrievalAdapter:
    provider = "immich"
    _TIMEOUT = (3, 7)

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def search_resources(
        self,
        *,
        query: str,
        limit: int,
    ) -> tuple[ProviderRetrievalHit, ...]:
        try:
            response = requests.post(
                f"{self._base_url}/api/search/smart",
                headers={"x-api-key": self._api_key},
                json={"query": query, "page": 1, "size": limit},
                timeout=self._TIMEOUT,
            )
            response.raise_for_status()
        except requests.Timeout as error:
            raise ProviderUnavailableError(
                "Immich semantic retrieval timed out"
            ) from error
        except requests.ConnectionError as error:
            raise ProviderUnavailableError(
                "Immich semantic retrieval is unavailable"
            ) from error
        except requests.HTTPError as error:
            status = getattr(error.response, "status_code", None)
            if status in {400, 404, 422}:
                raise ProviderCapabilityUnavailableError(
                    "Immich semantic retrieval capability is unavailable"
                ) from error
            raise ProviderUnavailableError(
                "Immich semantic retrieval is unavailable"
            ) from error
        except requests.RequestException as error:
            raise ProviderUnavailableError(
                "Immich semantic retrieval is unavailable"
            ) from error

        try:
            payload = response.json()
        except (TypeError, ValueError) as error:
            raise ProviderInvalidResponseError(
                "Immich semantic retrieval returned invalid JSON"
            ) from error

        items = self._items(payload)
        seen_locators: set[str] = set()
        hits: list[ProviderRetrievalHit] = []
        for rank, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ProviderInvalidResponseError(
                    "Immich semantic retrieval returned an invalid asset"
                )
            provider_locator = item.get("id")
            if (
                not isinstance(provider_locator, str)
                or not provider_locator.strip()
            ):
                raise ProviderInvalidResponseError(
                    "Immich semantic retrieval asset has no valid id"
                )
            if provider_locator in seen_locators:
                continue
            seen_locators.add(provider_locator)
            hits.append(
                ProviderRetrievalHit(
                    provider=self.provider,
                    provider_locator=provider_locator,
                    rank=rank,
                    provider_score=None,
                )
            )
        return tuple(hits)

    @staticmethod
    def _items(payload: object) -> list[Any]:
        if not isinstance(payload, dict):
            raise ProviderInvalidResponseError(
                "Immich semantic retrieval response must be an object"
            )
        assets = payload.get("assets")
        if not isinstance(assets, dict):
            raise ProviderInvalidResponseError(
                "Immich semantic retrieval response has no assets object"
            )
        items = assets.get("items")
        if not isinstance(items, list):
            raise ProviderInvalidResponseError(
                "Immich semantic retrieval response has no items list"
            )
        return items
