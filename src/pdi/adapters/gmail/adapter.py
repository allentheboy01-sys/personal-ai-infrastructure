import base64
import binascii
import logging
from pathlib import Path
from typing import Any, Iterable
import urllib.parse

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
import requests

from pdi.adapters.base import Adapter, ProviderFact


logger = logging.getLogger(__name__)

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
DEFAULT_TOKEN_FILE = "/etc/pdi/gmail-oauth-token.json"


class GmailAdapterError(RuntimeError):
    """Sanitized Gmail read failure."""


class GmailAdapter(Adapter):
    provider_name = "gmail"
    _BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"
    _PAGE_SIZE = 500

    def __init__(
        self,
        token_file: str = DEFAULT_TOKEN_FILE,
        *,
        session: requests.Session | None = None,
        base_url: str = _BASE_URL,
    ) -> None:
        self._token_file = token_file
        self._base_url = base_url.rstrip("/")
        self._session = session

    def connect(self) -> None:
        logger.info("Connecting Gmail read-only adapter")
        self._get_json("/profile", params={"fields": "historyId"})
        logger.info("Connected to Gmail read-only adapter")

    def scan(self) -> Iterable[ProviderFact]:
        """Return a complete, validated includeSpamTrash inventory."""

        messages: list[dict[str, Any]] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()

        while True:
            params = {
                "includeSpamTrash": "true",
                "maxResults": self._PAGE_SIZE,
                "fields": "messages(id),nextPageToken",
            }
            if page_token is not None:
                params["pageToken"] = page_token
            payload = self._get_json("/messages", params=params)
            page = payload.get("messages", [])
            if not isinstance(page, list):
                raise GmailAdapterError("Gmail inventory response is invalid")
            for item in page:
                if not isinstance(item, dict):
                    raise GmailAdapterError(
                        "Gmail inventory response is invalid"
                    )
                external_id = item.get("id")
                if not isinstance(external_id, str) or not external_id:
                    raise GmailAdapterError(
                        "Gmail inventory message identity is invalid"
                    )
                messages.append({"id": external_id})

            next_token = payload.get("nextPageToken")
            if next_token is None:
                break
            if not isinstance(next_token, str) or not next_token:
                raise GmailAdapterError("Gmail pagination token is invalid")
            if next_token in seen_tokens:
                raise GmailAdapterError("Gmail pagination token repeated")
            seen_tokens.add(next_token)
            page_token = next_token

        facts = [self._metadata_fact(item["id"]) for item in messages]
        logger.info("Gmail scan completed facts=%d", len(facts))
        return facts

    def open(self, fact: ProviderFact) -> Iterable[bytes]:
        if fact.provider != self.provider_name or fact.kind != "message":
            raise ValueError("ProviderFact is not a Gmail Message")
        if not isinstance(fact.external_id, str) or not fact.external_id:
            raise ValueError("ProviderFact has no valid Gmail identity")
        encoded_id = urllib.parse.quote(fact.external_id, safe="")
        payload = self._get_json(
            f"/messages/{encoded_id}",
            params={"format": "raw", "fields": "raw"},
        )
        encoded = payload.get("raw")
        if not isinstance(encoded, str) or not encoded:
            raise GmailAdapterError("Gmail RAW response is invalid")
        try:
            decoded = base64.b64decode(
                encoded + "=" * (-len(encoded) % 4),
                altchars=b"-_",
                validate=True,
            )
        except (binascii.Error, ValueError, TypeError):
            raise GmailAdapterError("Gmail RAW response is invalid") from None
        if not decoded:
            raise GmailAdapterError("Gmail RAW response is empty")
        yield decoded

    def _metadata_fact(self, external_id: str) -> ProviderFact:
        encoded_id = urllib.parse.quote(external_id, safe="")
        payload = self._get_json(
            f"/messages/{encoded_id}",
            params=[
                ("format", "metadata"),
                ("metadataHeaders", "Subject"),
                ("fields", "id,internalDate,payload(headers)"),
            ],
        )
        if payload.get("id") != external_id:
            raise GmailAdapterError("Gmail metadata identity is invalid")
        internal_date = payload.get("internalDate")
        if (
            not isinstance(internal_date, str)
            or not internal_date.isdecimal()
        ):
            raise GmailAdapterError("Gmail internalDate is invalid")
        subject = self._subject(payload.get("payload"))
        return ProviderFact(
            provider=self.provider_name,
            kind="message",
            external_id=external_id,
            name=subject,
            attributes={
                "path": None,
                "size": None,
                "mime_type": "message/rfc822",
                "version_tag": None,
                "content_hash": None,
            },
            raw={"internalDate": internal_date},
        )

    @staticmethod
    def _subject(payload: object) -> str | None:
        if not isinstance(payload, dict):
            raise GmailAdapterError("Gmail metadata payload is invalid")
        headers = payload.get("headers", [])
        if not isinstance(headers, list):
            raise GmailAdapterError("Gmail metadata headers are invalid")
        subjects = []
        for item in headers:
            if not isinstance(item, dict):
                raise GmailAdapterError("Gmail metadata headers are invalid")
            if str(item.get("name", "")).lower() == "subject":
                value = item.get("value")
                if isinstance(value, str) and value.strip():
                    subjects.append(value.strip())
        if len(subjects) > 1:
            raise GmailAdapterError("Gmail Subject header is ambiguous")
        return subjects[0] if subjects else None

    def _get_json(self, path: str, *, params: object) -> dict[str, Any]:
        try:
            response = self._authorized_session().get(
                f"{self._base_url}{path}",
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            raise GmailAdapterError("Gmail read-only API request failed") from None
        if not isinstance(payload, dict):
            raise GmailAdapterError("Gmail API response is invalid")
        return payload

    def _authorized_session(self) -> requests.Session:
        if self._session is not None:
            return self._session
        try:
            credentials = Credentials.from_authorized_user_file(
                str(Path(self._token_file)),
                scopes=[GMAIL_READONLY_SCOPE],
            )
        except (OSError, ValueError):
            raise GmailAdapterError("Gmail OAuth token is unavailable") from None
        if set(credentials.scopes or ()) != {GMAIL_READONLY_SCOPE}:
            raise GmailAdapterError("Gmail OAuth scope is invalid")
        self._session = AuthorizedSession(credentials)
        return self._session
