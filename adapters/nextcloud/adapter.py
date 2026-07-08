import os
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Iterable, Any

import requests

from adapters.base import Adapter, ProviderFact


class NextcloudAdapter(Adapter):
    provider_name = "nextcloud"

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password

    def connect(self) -> None:
        url = f"{self.base_url}/status.php"

        response = requests.get(
            url,
            auth=(self.username, self.password),
            timeout=10,
        )

        response.raise_for_status()

    def scan(self, path: str = "") -> Iterable[ProviderFact]:
        return self._propfind(path)

    def _propfind(self, path: str) -> list[ProviderFact]:
        encoded_path = urllib.parse.quote(path.strip("/"))
        url = f"{self.base_url}/remote.php/dav/files/{self.username}/"

        if encoded_path:
            url += encoded_path + "/"

        headers = {
            "Depth": "1",
            "Content-Type": "application/xml",
        }

        body = """<?xml version="1.0"?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:getcontentlength />
    <d:getcontenttype />
    <d:getetag />
    <d:getlastmodified />
    <d:resourcetype />
  </d:prop>
</d:propfind>
"""

        response = requests.request(
            "PROPFIND",
            url,
            headers=headers,
            data=body,
            auth=(self.username, self.password),
            timeout=10,
        )

        response.raise_for_status()

        return self._parse_webdav_response(response.text)

    def _parse_webdav_response(self, xml_text: str) -> list[ProviderFact]:
        namespace = {"d": "DAV:"}
        root = ET.fromstring(xml_text)

        facts: list[ProviderFact] = []

        for item in root.findall("d:response", namespace):
            href = self._get_text(item, "d:href", namespace)
            path = self._clean_href(href)
            if path == "":
                continue

            prop = item.find("d:propstat/d:prop", namespace)
            if prop is None:
                continue

            resource_type = prop.find("d:resourcetype", namespace)
            is_collection = (
                resource_type is not None
                and resource_type.find("d:collection", namespace) is not None
            )

            size_text = self._get_text(prop, "d:getcontentlength", namespace)
            size = int(size_text) if size_text else None

            name = path.rstrip("/").split("/")[-1] if path else None

            mime_type = self._get_text(prop, "d:getcontenttype", namespace)
            modified_at = self._get_text(prop, "d:getlastmodified", namespace)
            etag = self._get_text(prop, "d:getetag", namespace)

            facts.append(
                ProviderFact(
                    provider=self.provider_name,
                    kind="folder" if is_collection else "file",
                    external_id=href,
                    name=name,
                    attributes={
                        "path": path,
                        "size": size,
                        "mime_type": mime_type,
                        "modified_at": modified_at,
                        "etag": etag,
                    },
                    raw={
                        "href": href,
                        "is_collection": is_collection,
                    },
                )
            )

        return facts

    def _clean_href(self, href: str | None) -> str | None:
        if href is None:
            return None

        prefix = f"/remote.php/dav/files/{self.username}/"

        decoded = urllib.parse.unquote(href)

        if decoded.startswith(prefix):
            return decoded[len(prefix):]

        return decoded

    @staticmethod
    def _get_text(element: ET.Element, path: str, namespace: dict[str, str]) -> str | None:
        found = element.find(path, namespace)
        if found is None:
            return None
        return found.text


if __name__ == "__main__":
    adapter = NextcloudAdapter(
        base_url=os.environ["NEXTCLOUD_URL"],
        username=os.environ["NEXTCLOUD_USER"],
        password=os.environ["NEXTCLOUD_PASSWORD"],
    )

    adapter.connect()

    for fact in adapter.scan():
        print(f"[{fact.kind.upper()}] {fact.attributes.get('path')}")
        print(f"  name={fact.name}")
        print(f"  size={fact.attributes.get('size')}")
        print(f"  mime={fact.attributes.get('mime_type')}")
        print(f"  etag={fact.attributes.get('etag')}")
        print(f"  modified={fact.attributes.get('modified_at')}")
        print()