import base64

import pytest

from pdi.adapters.base import ProviderFact
from pdi.adapters.gmail import GmailAdapter, GmailAdapterError


class _Response:
    def __init__(self, payload, *, error=False):
        self._payload = payload
        self._error = error

    def raise_for_status(self):
        if self._error:
            import requests

            raise requests.HTTPError("private provider response")

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        return self.responses.pop(0)


def test_complete_inventory_is_paginated_and_metadata_is_allowlisted():
    session = _Session(
        [
            _Response({"messages": [{"id": "synthetic-a"}], "nextPageToken": "p2"}),
            _Response({"messages": [{"id": "synthetic-b"}]}),
            _Response({"id": "synthetic-a", "internalDate": "1000", "payload": {"headers": [{"name": "Subject", "value": "Display only"}]}}),
            _Response({"id": "synthetic-b", "internalDate": "2000", "payload": {"headers": []}}),
        ]
    )
    facts = list(GmailAdapter(session=session).scan())
    assert [fact.external_id for fact in facts] == ["synthetic-a", "synthetic-b"]
    assert all(fact.kind == "message" and fact.provider == "gmail" for fact in facts)
    assert facts[0].name == "Display only"
    assert facts[0].raw == {"internalDate": "1000"}
    assert set(facts[0].attributes) == {"path", "size", "mime_type", "version_tag", "content_hash"}
    assert session.calls[0][1]["includeSpamTrash"] == "true"
    assert session.calls[1][1]["pageToken"] == "p2"


def test_raw_base64url_decodes_exactly():
    raw = b"Subject: Synthetic\r\n\r\nBody\x00\xff"
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    session = _Session([_Response({"raw": encoded})])
    fact = ProviderFact("gmail", "message", "synthetic", None, {}, {})
    assert b"".join(GmailAdapter(session=session).open(fact)) == raw
    assert session.calls[0][1] == {"format": "raw", "fields": "raw"}


def test_pagination_failure_is_sanitized_and_yields_no_partial_inventory():
    session = _Session([
        _Response({"messages": [{"id": "must-not-leak"}], "nextPageToken": "p2"}),
        _Response({}, error=True),
    ])
    with pytest.raises(GmailAdapterError) as caught:
        list(GmailAdapter(session=session).scan())
    assert "must-not-leak" not in str(caught.value)
    assert "private provider response" not in str(caught.value)


def test_repeated_pagination_token_is_rejected():
    session = _Session([
        _Response({"messages": [], "nextPageToken": "same"}),
        _Response({"messages": [], "nextPageToken": "same"}),
    ])
    with pytest.raises(GmailAdapterError, match="pagination token repeated"):
        list(GmailAdapter(session=session).scan())
