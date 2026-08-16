import pytest

from pdi.adapters.base import ProviderFact
from pdi.adapters.nextcloud.adapter import NextcloudAdapter
from pdi.engine import SyncEngine
from pdi.identity import Matcher
from pdi.models import Asset, AssetSource, Blob
from pdi.repository import InMemoryRepository


def _seed_source(
    repository: InMemoryRepository,
    *,
    provider: str,
    external_id: str,
    path: str,
    name: str,
    version_tag: str,
    metadata: dict | None = None,
) -> AssetSource:
    asset = Asset(title=name)
    blob = Blob(
        asset_id=asset.id,
        hash=f"hash-{external_id}",
        size=10,
        mime_type="text/plain",
    )
    source = AssetSource(
        blob_id=blob.id,
        provider=provider,
        external_id=external_id,
        path=path,
        name=name,
        version_tag=version_tag,
        metadata=metadata or {},
    )
    repository.assets[asset.id] = asset
    repository.blobs[blob.id] = blob
    repository.sources[source.id] = source
    return source


def _nextcloud_fact(
    *,
    external_id: str,
    path: str,
    kind: str = "file",
) -> ProviderFact:
    name = path.rstrip("/").split("/")[-1]
    raw = {
        "href": f"/remote.php/dav/files/test-user/{path}",
        "oc_id": external_id,
        "file_id": f"file-{external_id}",
        "is_collection": kind == "folder",
    }
    return ProviderFact(
        provider="nextcloud",
        kind=kind,
        external_id=external_id,
        name=name,
        attributes={
            "path": path,
            "size": 10,
            "mime_type": "text/plain",
            "modified_at": None,
            "version_tag": f"version-{external_id}",
            "content_hash": None,
        },
        raw=raw,
    )


def test_partial_recursive_failure_does_not_deactivate_sources(
    monkeypatch,
) -> None:
    repository = InMemoryRepository()
    existing_source = _seed_source(
        repository,
        provider="nextcloud",
        external_id="nested-existing",
        path="A/existing.md",
        name="existing.md",
        version_tag="version-nested-existing",
    )
    adapter = NextcloudAdapter(
        base_url="https://nextcloud.example",
        username="test-user",
        password="test-password",
    )
    folder = _nextcloud_fact(
        external_id="folder-a",
        path="A/",
        kind="folder",
    )

    monkeypatch.setattr(adapter, "connect", lambda: None)

    def failing_propfind(path: str) -> list[ProviderFact]:
        if path == "":
            return [folder]

        raise RuntimeError("nested PROPFIND failed")

    monkeypatch.setattr(adapter, "_propfind", failing_propfind)

    sync_engine = SyncEngine(
        adapter=adapter,
        matcher=Matcher(),
        repository=repository,
    )

    with pytest.raises(
        RuntimeError,
        match="nested PROPFIND failed",
    ):
        sync_engine.sync_once()

    saved_source = repository.find_source(
        provider="nextcloud",
        external_id="nested-existing",
    )
    assert saved_source is existing_source
    assert saved_source.is_active is True
    assert saved_source.deleted_at is None


def test_complete_recursive_scan_deactivates_genuinely_missing_source(
    monkeypatch,
) -> None:
    repository = InMemoryRepository()
    seen_fact = _nextcloud_fact(
        external_id="seen-file",
        path="seen.md",
    )
    seen_source = _seed_source(
        repository,
        provider="nextcloud",
        external_id="seen-file",
        path="seen.md",
        name="seen.md",
        version_tag="version-seen-file",
        metadata=seen_fact.raw,
    )
    missing_source = _seed_source(
        repository,
        provider="nextcloud",
        external_id="missing-file",
        path="missing.md",
        name="missing.md",
        version_tag="version-missing-file",
    )
    adapter = NextcloudAdapter(
        base_url="https://nextcloud.example",
        username="test-user",
        password="test-password",
    )

    monkeypatch.setattr(adapter, "connect", lambda: None)
    monkeypatch.setattr(
        adapter,
        "_propfind",
        lambda path: [seen_fact],
    )
    monkeypatch.setattr(
        adapter,
        "open",
        lambda fact: pytest.fail(
            "Unchanged source must not be opened"
        ),
    )

    SyncEngine(
        adapter=adapter,
        matcher=Matcher(),
        repository=repository,
    ).sync_once()

    assert seen_source.is_active is True
    assert missing_source.is_active is False
    assert missing_source.deleted_at is not None


def test_unchanged_immich_asset_does_not_open_or_duplicate(
) -> None:
    repository = InMemoryRepository()
    raw = {
        "checksum": "provider-sha1",
        "checksum_algorithm": "sha1",
        "checksum_encoding": "base64",
        "width": 100,
        "height": 100,
        "exif": {},
        "favorite": False,
        "archived": False,
        "trashed": False,
        "visibility": "timeline",
        "duration": "0:00:00.00000",
        "isEdited": False,
    }
    source = _seed_source(
        repository,
        provider="immich",
        external_id="asset-1",
        path="/library/photo.jpg",
        name="photo.jpg",
        version_tag="2026-08-10T00:00:00.000Z",
        metadata=raw,
    )
    fact = ProviderFact(
        provider="immich",
        kind="file",
        external_id="asset-1",
        name="photo.jpg",
        attributes={
            "path": "/library/photo.jpg",
            "size": 10,
            "mime_type": "image/jpeg",
            "version_tag": "2026-08-10T00:00:00.000Z",
            "content_hash": None,
        },
        raw=dict(raw),
    )

    class FakeImmichAdapter:
        provider_name = "immich"

        def connect(self) -> None:
            return None

        def scan(self) -> list[ProviderFact]:
            return [fact]

        def open(self, fact: ProviderFact):
            pytest.fail("Unchanged Immich asset must not be opened")

    counts_before = (
        len(repository.assets),
        len(repository.blobs),
        len(repository.sources),
    )
    source_id = source.id
    blob_id = source.blob_id

    SyncEngine(
        adapter=FakeImmichAdapter(),
        matcher=Matcher(),
        repository=repository,
    ).sync_once()

    saved_source = repository.find_source(
        provider="immich",
        external_id="asset-1",
    )
    assert saved_source is not None
    assert saved_source.id == source_id
    assert saved_source.blob_id == blob_id
    assert (
        len(repository.assets),
        len(repository.blobs),
        len(repository.sources),
    ) == counts_before


def test_same_version_new_curated_metadata_updates_source_without_open(
) -> None:
    repository = InMemoryRepository()
    original_metadata = {
        "href": "/remote.php/dav/files/test-user/report.md",
        "oc_id": "report-source",
        "file_id": "file-report-source",
        "is_collection": False,
    }
    source = _seed_source(
        repository,
        provider="nextcloud",
        external_id="report-source",
        path="report.md",
        name="report.md",
        version_tag="version-report-source",
        metadata=original_metadata,
    )
    fact = _nextcloud_fact(
        external_id="report-source",
        path="report.md",
    )
    fact.raw["getlastmodified"] = (
        "Sun, 10 Aug 2026 00:00:00 GMT"
    )

    class FakeNextcloudAdapter:
        provider_name = "nextcloud"

        def connect(self) -> None:
            return None

        def scan(self) -> list[ProviderFact]:
            return [fact]

        def open(self, fact: ProviderFact):
            pytest.fail("Metadata-only reconciliation must not open content")

    counts_before = (
        len(repository.assets),
        len(repository.blobs),
        len(repository.sources),
    )
    source_id = source.id
    blob_id = source.blob_id

    SyncEngine(
        adapter=FakeNextcloudAdapter(),
        matcher=Matcher(),
        repository=repository,
    ).sync_once()

    saved_source = repository.find_source(
        provider="nextcloud",
        external_id="report-source",
    )
    assert saved_source is not None
    assert saved_source.id == source_id
    assert saved_source.blob_id == blob_id
    assert saved_source.version_tag == "version-report-source"
    assert saved_source.metadata == {
        **original_metadata,
        "getlastmodified": "Sun, 10 Aug 2026 00:00:00 GMT",
    }
    assert (
        len(repository.assets),
        len(repository.blobs),
        len(repository.sources),
    ) == counts_before
