import urllib.parse
import xml.etree.ElementTree as ET
from typing import Iterable

import requests

from pdi.adapters.base import Adapter, ProviderFact


class NextcloudAdapter(Adapter):
    provider_name = "nextcloud"

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password

    def connect(self) -> None:
        """连接 Nextcloud，并验证地址和凭据是否有效。"""
        url = f"{self.base_url}/status.php"

        response = requests.get(
            url,
            auth=(self.username, self.password),
            timeout=10,
        )

        response.raise_for_status()

    def scan(self, path: str = "") -> Iterable[ProviderFact]:
        """扫描指定 Nextcloud 目录中的直接子项。"""
        return self._propfind(path)

    def open(
        self,
        fact: ProviderFact,
    ) -> Iterable[bytes]:
        if fact.provider != self.provider_name:
            raise ValueError(
                f"ProviderFact belongs to {fact.provider}, "
                f"not {self.provider_name}"
            )

        if fact.kind != "file":
            raise ValueError("Only files can be opened")

        href = fact.raw.get("href")
        if not isinstance(href, str) or not href:
            raise ValueError("ProviderFact does not contain a valid href")

        url = f"{self.base_url}{href}"

        response = requests.get(
            url,
            auth=(self.username, self.password),
            stream=True,
            timeout=30,
        )

        response.raise_for_status()

        try:
            for chunk in response.iter_content(
                chunk_size=1024 * 1024,
            ):
                if chunk:
                    yield chunk
        finally:
            response.close()

    def _propfind(self, path: str) -> list[ProviderFact]:
        """向 Nextcloud WebDAV 发送 PROPFIND 请求。"""
        encoded_path = urllib.parse.quote(path.strip("/"))

        url = (
            f"{self.base_url}"
            f"/remote.php/dav/files/{self.username}/"
        )

        if encoded_path:
            url += encoded_path + "/"

        headers = {
            "Depth": "1",
            "Content-Type": "application/xml",
        }

        body = """<?xml version="1.0" encoding="UTF-8"?>
<d:propfind
    xmlns:d="DAV:"
    xmlns:oc="http://owncloud.org/ns">
  <d:prop>
    <oc:id />
    <oc:fileid />
    <d:getcontentlength />
    <d:getcontenttype />
    <d:getetag />
    <d:getlastmodified />
    <d:resourcetype />
  </d:prop>
</d:propfind>
"""

        response = requests.request(
            method="PROPFIND",
            url=url,
            headers=headers,
            data=body,
            auth=(self.username, self.password),
            timeout=10,
        )

        response.raise_for_status()

        return self._parse_webdav_response(response.text)

    def _parse_webdav_response(
        self,
        xml_text: str,
    ) -> list[ProviderFact]:
        """把 Nextcloud WebDAV XML 转换成统一的 ProviderFact。"""
        namespace = {
            "d": "DAV:",
            "oc": "http://owncloud.org/ns",
        }

        root = ET.fromstring(xml_text)

        facts: list[ProviderFact] = []

        for item in root.findall("d:response", namespace):
            href = self._get_text(
                item,
                "d:href",
                namespace,
            )

            path = self._clean_href(href)

            # PROPFIND Depth=1 通常也会返回被扫描目录本身。
            if path == "":
                continue

            prop = item.find(
                "d:propstat/d:prop",
                namespace,
            )

            if prop is None:
                continue

            resource_type = prop.find(
                "d:resourcetype",
                namespace,
            )

            is_collection = (
                resource_type is not None
                and resource_type.find(
                    "d:collection",
                    namespace,
                )
                is not None
            )

            oc_id = self._get_text(
                prop,
                "oc:id",
                namespace,
            )

            file_id = self._get_text(
                prop,
                "oc:fileid",
                namespace,
            )

            size_text = self._get_text(
                prop,
                "d:getcontentlength",
                namespace,
            )

            size = int(size_text) if size_text else None

            name = (
                path.rstrip("/").split("/")[-1]
                if path
                else None
            )

            mime_type = self._get_text(
                prop,
                "d:getcontenttype",
                namespace,
            )

            modified_at = self._get_text(
                prop,
                "d:getlastmodified",
                namespace,
            )

            etag = self._get_text(
                prop,
                "d:getetag",
                namespace,
            )

            facts.append(
                ProviderFact(
                    provider=self.provider_name,
                    kind=(
                        "folder"
                        if is_collection
                        else "file"
                    ),

                    # oc:id 在 Nextcloud 实例标识的基础上，
                    # 对 fileid 进行了命名空间处理。
                    external_id=oc_id,

                    name=name,

                    # attributes 中保存已经标准化的数据。
                    attributes={
                        "path": path,
                        "size": size,
                        "mime_type": mime_type,
                        "modified_at": modified_at,

                        # Nextcloud ETag 只作为 Provider 版本标识，
                        # 不能作为跨 Provider 内容 Hash。
                        "version_tag": etag,

                        # 当前 Adapter 还没有下载内容计算 Hash。
                        "content_hash": None,
                    },

                    # raw 中保存 Provider 原始或特有数据，
                    # Identity 不应该直接依赖这些字段。
                    raw={
                        "href": href,
                        "oc_id": oc_id,
                        "file_id": file_id,
                        "is_collection": is_collection,
                    },
                )
            )

        return facts

    def _clean_href(
        self,
        href: str | None,
    ) -> str | None:
        """把 WebDAV href 转换为用户目录内的相对路径。"""
        if href is None:
            return None

        prefix = (
            f"/remote.php/dav/files/"
            f"{self.username}/"
        )

        decoded = urllib.parse.unquote(href)

        if decoded.startswith(prefix):
            return decoded[len(prefix):]

        return decoded

    @staticmethod
    def _get_text(
        element: ET.Element,
        path: str,
        namespace: dict[str, str],
    ) -> str | None:
        found = element.find(
            path,
            namespace,
        )

        if found is None:
            return None

        return found.text


