from typing import Any

import requests

from .models import EnumerablePersonInventory


class ImmichEnumerablePeopleAdapter:
    provider = "immich"
    _PAGE_SIZE = 1000

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"x-api-key": api_key}

    def connect(self) -> None:
        response = requests.get(
            f"{self._base_url}/api/server/about",
            headers=self._headers,
            timeout=10,
        )
        response.raise_for_status()

    def scan(self) -> EnumerablePersonInventory:
        page = 1
        external_ids: list[str] = []
        seen: set[str] = set()
        reported_total: int | None = None

        while True:
            response = requests.get(
                f"{self._base_url}/api/people",
                headers=self._headers,
                params={
                    "withHidden": "true",
                    "page": page,
                    "size": self._PAGE_SIZE,
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = self._payload(response.json())
            total = payload.get("total")
            if isinstance(total, bool) or not isinstance(total, int) or total < 0:
                raise ValueError("Immich People response has invalid total")
            if reported_total is None:
                reported_total = total
            elif total != reported_total:
                raise ValueError("Immich People total changed during scan")

            for item in payload["people"]:
                if not isinstance(item, dict):
                    raise ValueError("Immich People item must be an object")
                external_id = item.get("id")
                if not isinstance(external_id, str) or not external_id.strip():
                    raise ValueError("Immich Person has invalid id")
                if external_id in seen:
                    raise ValueError("Immich People scan returned duplicate id")
                seen.add(external_id)
                external_ids.append(external_id)

            has_next = payload.get("hasNextPage")
            if not isinstance(has_next, bool):
                raise ValueError("Immich People response has invalid hasNextPage")
            if not has_next:
                break
            page += 1

        return EnumerablePersonInventory(
            provider=self.provider,
            external_ids=tuple(external_ids),
            reported_total=reported_total if reported_total is not None else 0,
        )

    @staticmethod
    def _payload(value: object) -> dict[str, Any]:
        if not isinstance(value, dict) or not isinstance(value.get("people"), list):
            raise ValueError("Immich People response has invalid shape")
        return value
