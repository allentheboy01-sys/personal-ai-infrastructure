import pytest
from dataclasses import fields
from datetime import UTC, datetime

from pdi.adapters.base import (
    ProviderFact,
    ProviderResourceDisappearedError,
)
from pdi.adapters.nextcloud.adapter import NextcloudAdapter
from pdi.engine import (
    DiscoveryBatch,
    DiscoveryMode,
    IncompleteProviderSyncError,
    MissingNextCheckpointError,
    SyncEngine,
)
from pdi.identity import Matcher
from pdi.models import Asset, AssetSource, Blob
from pdi.repository import InMemoryRepository
from pdi.sync_state import ProviderSyncState


class _MemorySyncStateRepository:
    def __init__(self) -> None:
        self.state: ProviderSyncState | None = None

    def get_or_create(self, provider: str, mechanism: str) -> ProviderSyncState:
        if self.state is None:
            now = datetime.now(UTC)
            self.state = ProviderSyncState(
                provider,
                mechanism,
                None,
                0,
                False,
                now,
                now,
            )
        return self.state

    def read(self, provider: str, mechanism: str):
        return self.state

    def compare_and_swap_checkpoint(
        self,
        provider: str,
        mechanism: str,
        *,
        expected_version: int,
        checkpoint: str,
    ):
        if not isinstance(checkpoint, str) or not checkpoint:
            raise ValueError("trusted checkpoint required")
        state = self.get_or_create(provider, mechanism)
        if state.version != expected_version:
            return None
        self.state = ProviderSyncState(
            provider,
            mechanism,
            checkpoint,
            expected_version + 1,
            False,
            state.created_at,
            datetime.now(UTC),
        )
        return self.state

    def recover_after_reconciliation(
        self,
        provider: str,
        mechanism: str,
        *,
        expected_version: int,
        trusted_checkpoint: str,
    ):
        if not isinstance(trusted_checkpoint, str) or not trusted_checkpoint:
            raise ValueError("trusted checkpoint required")
        state = self.get_or_create(provider, mechanism)
        if state.version != expected_version:
            return None
        self.state = ProviderSyncState(
            provider,
            mechanism,
            trusted_checkpoint,
            expected_version + 1,
            False,
            state.created_at,
            datetime.now(UTC),
        )
        return self.state

    def mark_reconciliation_required(
        self,
        provider: str,
        mechanism: str,
        *,
        expected_version: int,
    ):
        state = self.get_or_create(provider, mechanism)
        if state.version != expected_version:
            return None
        self.state = ProviderSyncState(
            provider,
            mechanism,
            state.checkpoint,
            expected_version + 1,
            True,
            state.created_at,
            datetime.now(UTC),
        )
        return self.state


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


def test_provider_fact_contract_excludes_discovery_mechanics() -> None:
    assert {field.name for field in fields(ProviderFact)} == {
        "provider",
        "kind",
        "external_id",
        "name",
        "attributes",
        "raw",
    }


def test_incremental_absence_never_deactivates_missing_sources() -> None:
    repository = InMemoryRepository()
    sources = {
        external_id: _seed_source(
            repository,
            provider="nextcloud",
            external_id=external_id,
            path=f"{external_id}.md",
            name=f"{external_id}.md",
            version_tag=f"version-{external_id}",
        )
        for external_id in ("a", "b", "c")
    }
    fact = _nextcloud_fact(external_id="a", path="a.md")

    class Adapter:
        provider_name = "nextcloud"

        def connect(self) -> None:
            return None

        def scan(self):
            pytest.fail("incremental sync must use the batch discovery callback")

        def open(self, fact):
            pytest.fail("unchanged Source must not be opened")

    state_repository = _MemorySyncStateRepository()
    advanced = SyncEngine(
        Adapter(),
        Matcher(),
        repository,
        state_repository,
    ).sync_incremental(
        "fake-window",
        lambda state: DiscoveryBatch(
            provider="nextcloud",
            mode=DiscoveryMode.INCREMENTAL_NON_AUTHORITATIVE,
            facts=(fact,),
            next_checkpoint="window-2",
        ),
    )

    assert advanced.checkpoint == "window-2"
    assert all(source.is_active for source in sources.values())


def test_incremental_missing_checkpoint_fails_before_applying_facts() -> None:
    repository = InMemoryRepository()
    state_repository = _MemorySyncStateRepository()
    state = state_repository.get_or_create("nextcloud", "fake-window")
    state_repository.compare_and_swap_checkpoint(
        "nextcloud",
        "fake-window",
        expected_version=state.version,
        checkpoint="cursor-a",
    )

    class Adapter:
        provider_name = "nextcloud"

        def connect(self) -> None:
            return None

        def scan(self):
            pytest.fail("incremental sync must not use full scan")

        def open(self, fact):
            yield b"data"

    with pytest.raises(MissingNextCheckpointError):
        SyncEngine(
            Adapter(), Matcher(), repository, state_repository
        ).sync_incremental(
            "fake-window",
            lambda state: DiscoveryBatch(
                provider="nextcloud",
                mode=DiscoveryMode.INCREMENTAL_NON_AUTHORITATIVE,
                facts=(_nextcloud_fact(external_id="a", path="a.md"),),
                next_checkpoint=None,
            ),
        )

    unchanged = state_repository.read("nextcloud", "fake-window")
    assert unchanged is not None
    assert unchanged.checkpoint == "cursor-a"
    assert unchanged.version == 1
    assert repository.find_source("nextcloud", "a") is None


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
    committed_a = _nextcloud_fact(
        external_id="committed-a",
        path="committed-a.md",
    )
    committed_b = _nextcloud_fact(
        external_id="committed-b",
        path="committed-b.md",
    )

    monkeypatch.setattr(adapter, "connect", lambda: None)
    monkeypatch.setattr(adapter, "open", lambda fact: [b"0123456789"])

    def failing_propfind(path: str) -> list[ProviderFact]:
        if path == "":
            return [committed_a, committed_b, folder]

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
    assert repository.find_source(
        provider="nextcloud",
        external_id="committed-a",
    ) is not None
    assert repository.find_source(
        provider="nextcloud",
        external_id="committed-b",
    ) is not None


def test_apply_failure_preserves_prior_fact_and_skips_reconciliation() -> None:
    class FailingRepository(InMemoryRepository):
        def __init__(self) -> None:
            super().__init__()
            self.execute_count = 0

        def execute(self, decision) -> None:
            self.execute_count += 1
            if self.execute_count == 2:
                raise RuntimeError("synthetic persistence failure")
            super().execute(decision)

    repository = FailingRepository()
    missing = _seed_source(
        repository,
        provider="nextcloud",
        external_id="existing-missing",
        path="existing-missing.md",
        name="existing-missing.md",
        version_tag="old",
    )
    facts = [
        _nextcloud_fact(external_id="first", path="first.md"),
        _nextcloud_fact(external_id="second", path="second.md"),
    ]
    adapter = _MutableProviderAdapter(facts, set())

    with pytest.raises(RuntimeError, match="persistence failure"):
        SyncEngine(adapter, Matcher(), repository).sync_once()

    assert repository.find_source("nextcloud", "first") is not None
    assert repository.find_source("nextcloud", "second") is None
    assert missing.is_active is True
    assert missing.deleted_at is None


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
    another_missing_source = _seed_source(
        repository,
        provider="nextcloud",
        external_id="another-missing-file",
        path="another-missing.md",
        name="another-missing.md",
        version_tag="version-another-missing-file",
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
    assert another_missing_source.is_active is False
    assert another_missing_source.deleted_at is not None


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


class _MutableProviderAdapter:
    provider_name = "nextcloud"

    def __init__(
        self,
        facts: list[ProviderFact],
        disappeared_external_ids: set[str],
    ) -> None:
        self._facts = facts
        self._disappeared_external_ids = disappeared_external_ids
        self.opened_external_ids: list[str | None] = []

    def connect(self) -> None:
        return None

    def scan(self):
        yield from self._facts

    def open(self, fact: ProviderFact):
        self.opened_external_ids.append(fact.external_id)
        if fact.external_id in self._disappeared_external_ids:
            raise ProviderResourceDisappearedError(self.provider_name)
        yield b"0123456789"


def test_disappeared_fact_marks_run_incomplete_but_later_fact_commits(
    caplog,
) -> None:
    repository = InMemoryRepository()
    unseen_source = _seed_source(
        repository,
        provider="nextcloud",
        external_id="unseen-existing",
        path="unseen-existing.md",
        name="unseen-existing.md",
        version_tag="prior-version",
    )
    private_path = "private-sensitive-name.md"
    disappeared = _nextcloud_fact(
        external_id="disappeared",
        path=private_path,
    )
    later = _nextcloud_fact(
        external_id="later-valid",
        path="later-valid.md",
    )
    adapter = _MutableProviderAdapter(
        [disappeared, later],
        {"disappeared"},
    )

    with pytest.raises(IncompleteProviderSyncError) as raised:
        SyncEngine(adapter, Matcher(), repository).sync_once()

    assert raised.value.provider == "nextcloud"
    assert raised.value.disappeared_count == 1
    assert private_path not in str(raised.value)
    assert private_path not in caplog.text
    assert repository.find_source(
        provider="nextcloud",
        external_id="disappeared",
    ) is None
    assert disappeared.attributes["content_hash"] is None
    assert repository.find_source(
        provider="nextcloud",
        external_id="later-valid",
    ) is not None
    assert unseen_source.is_active is True
    assert unseen_source.deleted_at is None
    assert adapter.opened_external_ids == ["disappeared", "later-valid"]


def test_renamed_replacement_processes_independently_but_run_is_incomplete(
) -> None:
    repository = InMemoryRepository()
    old_source = _seed_source(
        repository,
        provider="nextcloud",
        external_id="old-resource",
        path="old-name.md",
        name="old-name.md",
        version_tag="prior-version",
    )
    old_observation = _nextcloud_fact(
        external_id="old-resource",
        path="old-name.md",
    )
    replacement = _nextcloud_fact(
        external_id="replacement-resource",
        path="new-name.md",
    )
    adapter = _MutableProviderAdapter(
        [old_observation, replacement],
        {"old-resource"},
    )

    with pytest.raises(IncompleteProviderSyncError):
        SyncEngine(adapter, Matcher(), repository).sync_once()

    saved_old = repository.find_source(
        provider="nextcloud",
        external_id="old-resource",
    )
    assert saved_old is old_source
    assert saved_old.version_tag == "prior-version"
    assert saved_old.is_active is True
    assert repository.find_source(
        provider="nextcloud",
        external_id="replacement-resource",
    ) is not None


def test_failed_partial_run_is_idempotent_on_authoritative_rerun() -> None:
    repository = InMemoryRepository()
    genuinely_missing = _seed_source(
        repository,
        provider="nextcloud",
        external_id="genuinely-missing",
        path="genuinely-missing.md",
        name="genuinely-missing.md",
        version_tag="prior-version",
    )
    first_good = _nextcloud_fact(
        external_id="stable-resource",
        path="stable-resource.md",
    )
    disappeared = _nextcloud_fact(
        external_id="disappeared-resource",
        path="disappeared-resource.md",
    )

    with pytest.raises(IncompleteProviderSyncError):
        SyncEngine(
            _MutableProviderAdapter(
                [first_good, disappeared],
                {"disappeared-resource"},
            ),
            Matcher(),
            repository,
        ).sync_once()

    assert genuinely_missing.is_active is True
    assert genuinely_missing.deleted_at is None

    committed = repository.find_source(
        provider="nextcloud",
        external_id="stable-resource",
    )
    assert committed is not None
    committed_id = committed.id
    counts_after_partial = (
        len(repository.assets),
        len(repository.blobs),
        len(repository.sources),
    )

    second_good = _nextcloud_fact(
        external_id="stable-resource",
        path="stable-resource.md",
    )

    class AuthoritativeAdapter(_MutableProviderAdapter):
        def open(self, fact: ProviderFact):
            pytest.fail("Unchanged Resource must not be reopened on rerun")

    SyncEngine(
        AuthoritativeAdapter([second_good], set()),
        Matcher(),
        repository,
    ).sync_once()

    rerun_source = repository.find_source(
        provider="nextcloud",
        external_id="stable-resource",
    )
    assert rerun_source is not None
    assert rerun_source.id == committed_id
    assert (
        len(repository.assets),
        len(repository.blobs),
        len(repository.sources),
    ) == counts_after_partial
    assert sum(
        source.external_id == "stable-resource"
        for source in repository.sources.values()
    ) == 1
    assert genuinely_missing.is_active is False
    assert genuinely_missing.deleted_at is not None


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
