import logging
import urllib.parse
from typing import Any, Iterable

import requests

from pdi.adapters.base import Adapter, ProviderFact


logger = logging.getLogger(__name__)


class ImmichAdapter(Adapter):
    provider_name = "immich"
    _PAGE_SIZE = 1000

    def __init__(
        self,
        base_url: str,
        api_key: str,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def connect(self) -> None:
        """Connect to Immich and verify the API key."""

        logger.info("Connecting Immich...")

        response = requests.get(
            f"{self.base_url}/api/server/about",
            headers=self._headers(),
            timeout=10,
        )

        response.raise_for_status()

        logger.info("Connected to Immich")

    def scan(self) -> Iterable[ProviderFact]:
        """Scan every page returned by Immich metadata search."""

        logger.info("Scanning Immich...")

        facts: list[ProviderFact] = []
        page = 1
        seen_pages: set[int] = set()

        while page not in seen_pages:
            seen_pages.add(page)

            response = requests.post(
                f"{self.base_url}/api/search/metadata",
                headers=self._headers(),
                json={
                    "page": page,
                    "size": self._PAGE_SIZE,
                    "withExif": True,
                },
                timeout=30,
            )

            response.raise_for_status()
            assets_page = self._assets_page(response.json())

            for asset in assets_page["items"]:
                if not isinstance(asset, dict):
                    raise ValueError(
                        "Immich search response contains "
                        "a non-object asset"
                    )

                facts.append(
                    self._to_provider_fact(asset)
                )

            next_page = assets_page.get("nextPage")

            if next_page is None or next_page == "":
                break

            try:
                page = int(next_page)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "Immich search response contains "
                    "an invalid nextPage"
                ) from error

            if page < 1:
                raise ValueError(
                    "Immich search response contains "
                    "an invalid nextPage"
                )
        else:
            raise ValueError(
                "Immich search pagination repeated a page"
            )

        logger.info(
            "Found %d Immich assets",
            len(facts),
        )
        logger.info("Immich scan finished")

        return facts

    def open(
        self,
        fact: ProviderFact,
    ) -> Iterable[bytes]:
        """Stream the original bytes for one Immich asset."""

        if fact.provider != self.provider_name:
            raise ValueError(
                f"ProviderFact belongs to {fact.provider}, "
                f"not {self.provider_name}"
            )

        if fact.kind != "file":
            raise ValueError("Only files can be opened")

        if not isinstance(fact.external_id, str) or not fact.external_id:
            raise ValueError(
                "ProviderFact does not contain a valid external_id"
            )

        external_id = urllib.parse.quote(
            fact.external_id,
            safe="",
        )

        response = requests.get(
            f"{self.base_url}/api/assets/{external_id}/original",
            headers=self._headers(),
            stream=True,
            timeout=30,
        )

        try:
            response.raise_for_status()

            for chunk in response.iter_content(
                chunk_size=1024 * 1024,
            ):
                if chunk:
                    yield chunk
        finally:
            response.close()

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
        }

    @staticmethod
    def _assets_page(
        payload: object,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError(
                "Immich search response must be an object"
            )

        assets_page = payload.get("assets")

        if not isinstance(assets_page, dict):
            raise ValueError(
                "Immich search response does not contain assets"
            )

        if not isinstance(assets_page.get("items"), list):
            raise ValueError(
                "Immich search response assets must contain items"
            )

        return assets_page

    @classmethod
    def _to_provider_fact(
        cls,
        asset: dict[str, Any],
    ) -> ProviderFact:
        external_id = asset.get("id")

        if not isinstance(external_id, str) or not external_id:
            raise ValueError(
                "Immich asset does not contain a valid id"
            )

        exif_info = asset.get("exifInfo")

        if not isinstance(exif_info, dict):
            exif_info = {}

        file_size = exif_info.get("fileSizeInByte")

        if isinstance(file_size, bool):
            file_size = None
        elif isinstance(file_size, int):
            if file_size < 0:
                file_size = None
        elif isinstance(file_size, str) and file_size.isdecimal():
            file_size = int(file_size)
        else:
            file_size = None

        checksum = asset.get("checksum")

        if not isinstance(checksum, str):
            checksum = None

        # updatedAt is a temporary version candidate for the first
        # Immich adapter version and requires real-world smoke
        # validation. Metadata-only updates may trigger an additional
        # SHA-256 verification. Canonical identity is still determined
        # by the SHA-256 calculated later by SyncEngine.
        version_tag = asset.get("updatedAt")

        if not isinstance(version_tag, str):
            version_tag = None

        return ProviderFact(
            provider=cls.provider_name,
            kind="file",
            external_id=external_id,
            name=cls._optional_string(
                asset,
                "originalFileName",
            ),
            attributes={
                "path": cls._optional_string(
                    asset,
                    "originalPath",
                ),
                "size": file_size,
                "mime_type": cls._optional_string(
                    asset,
                    "originalMimeType",
                ),
                "version_tag": version_tag,
                "content_hash": None,
            },
            raw={
                "checksum": checksum,
                "checksum_algorithm": (
                    "sha1"
                    if checksum is not None
                    else None
                ),
                "checksum_encoding": (
                    "base64"
                    if checksum is not None
                    else None
                ),
                "width": asset.get("width"),
                "height": asset.get("height"),
                "exif": dict(exif_info),
                "favorite": asset.get("isFavorite"),
                "archived": asset.get("isArchived"),
                "trashed": asset.get("isTrashed"),
                "visibility": asset.get("visibility"),
                "duration": asset.get("duration"),
                "isEdited": asset.get("isEdited"),
            },
        )

    @staticmethod
    def _optional_string(
        source: dict[str, Any],
        key: str,
    ) -> str | None:
        value = source.get(key)

        if isinstance(value, str):
            return value

        return None
