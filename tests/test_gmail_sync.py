import hashlib
import logging

import pytest

from pdi.adapters.base import ProviderFact
from pdi.engine import SyncEngine
from pdi.identity import Matcher
from pdi.models import Asset, AssetSource, Blob, ResourceType
from pdi.repository import InMemoryRepository


def _fact(external_id, *, internal_date="1000"):
    return ProviderFact(
        "gmail", "message", external_id, "Synthetic subject",
        {"path": None, "size": None, "mime_type": "message/rfc822", "version_tag": None, "content_hash": None},
        {"internalDate": internal_date},
    )


class _Adapter:
    provider_name = "gmail"

    def __init__(self, facts, raw=b"Subject: Synthetic\r\n\r\nBody", *, fail=False):
        self.facts = facts
        self.raw = raw
        self.fail = fail

    def connect(self):
        pass

    def scan(self):
        if self.fail:
            raise RuntimeError("synthetic scan failure")
        return self.facts

    def open(self, fact):
        yield self.raw


def _sync(repository, facts, raw=b"Subject: Synthetic\r\n\r\nBody"):
    SyncEngine(_Adapter(facts, raw), Matcher(), repository).sync_once()


def test_message_identity_does_not_globally_merge_equal_raw():
    repository = InMemoryRepository()
    _sync(repository, [_fact("a"), _fact("b")])
    assert len(repository.assets) == len(repository.blobs) == len(repository.sources) == 2
    assert {asset.resource_type for asset in repository.assets.values()} == {ResourceType.MESSAGE}
    assert all(source.metadata == {"internalDate": "1000"} for source in repository.sources.values())


def test_same_message_reuses_asset_and_changed_raw_stays_in_asset():
    repository = InMemoryRepository()
    _sync(repository, [_fact("a")])
    source = repository.find_source("gmail", "a")
    original_asset = source.blob_id and repository.get_blob(source.blob_id).asset_id
    _sync(repository, [_fact("a")])
    assert len(repository.assets) == 1
    assert len(repository.blobs) == 1
    _sync(repository, [_fact("a", internal_date="2000")], raw=b"Subject: Changed\r\n\r\nNew")
    source = repository.find_source("gmail", "a")
    assert repository.get_blob(source.blob_id).asset_id == original_asset
    assert len(repository.assets) == 1
    assert len(repository.blobs) == 2


def test_legacy_message_blob_with_unknown_size_remains_usable():
    repository = InMemoryRepository()
    raw = b"Subject: Synthetic\r\n\r\nBody"
    digest = hashlib.sha256(raw).hexdigest()
    asset = Asset(resource_type=ResourceType.MESSAGE, title="Synthetic")
    blob = Blob(
        asset_id=asset.id,
        hash=digest,
        size=None,
        mime_type="message/rfc822",
    )
    source = AssetSource(
        blob_id=blob.id,
        provider="gmail",
        external_id="legacy-message",
        name="Synthetic subject",
        version_tag=digest,
        provider_mime_type=None,
        provider_size=None,
        metadata={"internalDate": "1000"},
    )
    repository.assets[asset.id] = asset
    repository.blobs[blob.id] = blob
    repository.sources[source.id] = source

    _sync(repository, [_fact("legacy-message")], raw=raw)

    saved = repository.find_source("gmail", "legacy-message")
    assert saved is not None
    assert saved.blob_id == blob.id
    assert saved.provider_mime_type == "message/rfc822"
    assert saved.provider_size is None
    assert repository.blobs[blob.id].size is None
    assert len(repository.assets) == 1
    assert len(repository.blobs) == 1


def test_complete_missing_deactivates_but_failed_scan_does_not():
    repository = InMemoryRepository()
    _sync(repository, [_fact("a"), _fact("b")])
    _sync(repository, [_fact("a")])
    assert repository.find_source("gmail", "b").is_active is False
    with pytest.raises(RuntimeError, match="synthetic scan failure"):
        SyncEngine(_Adapter([], fail=True), Matcher(), repository).sync_once()
    assert repository.find_source("gmail", "a").is_active is True


def test_sync_logs_do_not_expose_message_identity_title_or_content(caplog):
    repository = InMemoryRepository()
    fact = _fact("private-message-id")
    fact.name = "Private subject"
    with caplog.at_level(logging.DEBUG):
        _sync(repository, [fact], raw=b"Private raw content")
    rendered = caplog.text
    assert "private-message-id" not in rendered
    assert "Private subject" not in rendered
    assert "Private raw content" not in rendered
