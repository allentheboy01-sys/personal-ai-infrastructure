from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Connection

from pdi.adapters.base import ProviderFact
from pdi.adapters.nextcloud import (
    NEXTCLOUD_INCREMENTAL_MECHANISM,
    NextcloudActivityIncrementalSync,
)
from pdi.adapters.nextcloud.incremental import ActivityPage
from pdi.database import create_postgres_engine
from pdi.engine import InvalidCheckpointError, SyncEngine
from pdi.identity import Matcher
from pdi.repository import PostgreSQLRepository
from pdi.sync_state import PostgreSQLProviderSyncStateRepository
from tests.integration.database_guard import require_safe_test_database_url


ROOT = Path(__file__).resolve().parents[2]


def _config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture
def context():
    database_engine = create_postgres_engine(require_safe_test_database_url())
    with database_engine.connect() as connection:
        command.upgrade(_config(connection), "head")
    with database_engine.begin() as connection:
        connection.exec_driver_sql("TRUNCATE TABLE assets CASCADE")
        connection.exec_driver_sql("DELETE FROM provider_sync_state")
    adapter = _Adapter()
    repository = PostgreSQLRepository(database_engine)
    states = PostgreSQLProviderSyncStateRepository(database_engine)
    engine = SyncEngine(adapter, Matcher(), repository, states)
    service = NextcloudActivityIncrementalSync(adapter, engine, states)
    try:
        yield adapter, repository, states, engine, service
    finally:
        database_engine.dispose()


def _fact(external_id: str, path: str, *, folder: bool = False) -> ProviderFact:
    body = external_id.encode()
    return ProviderFact(
        provider="nextcloud",
        kind="folder" if folder else "file",
        external_id=external_id,
        name=path.rstrip("/").split("/")[-1],
        attributes={
            "path": path,
            "size": None if folder else len(body),
            "mime_type": None if folder else "text/plain",
            "modified_at": None,
            "version_tag": f"v-{external_id}",
            "content_hash": None,
        },
        raw={
            "href": f"/remote.php/dav/files/test-user/{path}",
            "oc_id": external_id,
            "file_id": f"file-{external_id}",
            "is_collection": folder,
        },
    )


def _activity(activity_id: int, file_id: str, path: str) -> dict:
    return {
        "activity_id": activity_id,
        "object_type": "files",
        "object_id": file_id,
        "object_name": path,
    }


class _Adapter:
    provider_name = "nextcloud"
    base_url = "https://nextcloud.example"
    username = "test-user"
    password = "test-password"

    def __init__(self):
        self.full_facts: Iterable[ProviderFact] = ()
        self.search_results = {}
        self.exact_results = {}
        self.subtrees = {}
        self.fail_exact_once = set()

    def connect(self):
        return None

    def scan(self, path=""):
        return self.subtrees.get(path, self.full_facts if not path else ())

    def open(self, fact):
        yield fact.external_id.encode()

    def search_by_fileid(self, file_id):
        return self.search_results.get(file_id)

    def propfind_exact(self, path):
        if path in self.fail_exact_once:
            self.fail_exact_once.remove(path)
            raise RuntimeError("targeted DAV failed")
        return self.exact_results.get(path)


def _checkpoint(states, value="100"):
    state = states.get_or_create("nextcloud", NEXTCLOUD_INCREMENTAL_MECHANISM)
    result = states.compare_and_swap_checkpoint(
        "nextcloud", NEXTCLOUD_INCREMENTAL_MECHANISM,
        expected_version=state.version, checkpoint=value,
    )
    assert result is not None


def _page(*activities, checkpoint="102"):
    return ActivityPage(tuple(activities), checkpoint)


def test_basic_incremental_and_rename_preserve_unseen_and_identity(
    context, monkeypatch
):
    adapter, repository, states, engine, service = context
    adapter.full_facts = tuple(_fact(v, f"{v}.txt") for v in "abc")
    engine.sync_once()
    original = repository.find_source("nextcloud", "a")
    _checkpoint(states)
    adapter.search_results = {
        "file-a": _fact("a", "renamed/a.txt"),
        "file-d": _fact("d", "d.txt"),
    }
    adapter.exact_results = {
        "renamed/a.txt": _fact("a", "renamed/a.txt"),
        "d.txt": _fact("d", "d.txt"),
    }
    monkeypatch.setattr(service, "_fetch_activity_page", lambda c: _page(
        _activity(101, "file-a", "old/a.txt"),
        _activity(102, "file-d", "d.txt"),
    ))
    result = service.run_incremental()
    assert result.checkpoint == "102"
    renamed = repository.find_source("nextcloud", "a")
    assert renamed is not None and original is not None
    assert renamed.id == original.id
    assert renamed.path == "renamed/a.txt"
    assert repository.find_source("nextcloud", "d") is not None
    assert repository.find_source("nextcloud", "b").is_active is True
    assert repository.find_source("nextcloud", "c").is_active is True


def test_delete_hint_is_not_tombstone_but_full_scope_absence_deactivates(
    context, monkeypatch
):
    adapter, repository, states, engine, service = context
    adapter.full_facts = (_fact("b", "b.txt"),)
    engine.sync_once()
    _checkpoint(states)
    monkeypatch.setattr(service, "_fetch_activity_page", lambda c: _page(
        _activity(101, "file-b", "b.txt"), checkpoint="101"
    ))
    service.run_incremental()
    assert repository.find_source("nextcloud", "b").is_active is True
    adapter.full_facts = ()
    engine.sync_once()
    assert repository.find_source("nextcloud", "b").is_active is False


def test_activity_return_to_scope_reactivates_same_source(context, monkeypatch):
    adapter, repository, states, engine, service = context
    adapter.full_facts = (_fact("b", "b.txt"),)
    engine.sync_once()
    original = repository.find_source("nextcloud", "b")
    adapter.full_facts = ()
    engine.sync_once()
    _checkpoint(states)
    adapter.search_results["file-b"] = _fact("b", "b.txt")
    adapter.exact_results["b.txt"] = _fact("b", "b.txt")
    monkeypatch.setattr(service, "_fetch_activity_page", lambda c: _page(
        _activity(101, "file-b", "b.txt"), checkpoint="101"
    ))
    service.run_incremental()
    returned = repository.find_source("nextcloud", "b")
    assert returned.id == original.id
    assert returned.blob_id == original.blob_id
    assert returned.is_active is True and returned.deleted_at is None


def test_folder_move_revalidates_only_subtree(context, monkeypatch):
    adapter, repository, states, engine, service = context
    adapter.full_facts = (_fact("one", "A/one.txt"), _fact("two", "A/two.txt"))
    engine.sync_once()
    original_ids = {
        v: repository.find_source("nextcloud", v).id for v in ("one", "two")
    }
    _checkpoint(states)
    adapter.search_results["500"] = _fact("folder", "B", folder=True)
    adapter.exact_results["B"] = _fact("folder", "B", folder=True)
    adapter.subtrees["B"] = (
        _fact("one", "B/one.txt"), _fact("two", "B/two.txt")
    )
    monkeypatch.setattr(service, "_fetch_activity_page", lambda c: _page(
        _activity(101, "500", "A"), checkpoint="101"
    ))
    service.run_incremental()
    for value in ("one", "two"):
        source = repository.find_source("nextcloud", value)
        assert source.id == original_ids[value]
        assert source.path == f"B/{value}.txt"


def test_partial_failure_replays_durable_facts_without_duplicates(
    context, monkeypatch
):
    adapter, repository, states, _, service = context
    _checkpoint(states)
    adapter.search_results = {
        "file-a": _fact("a", "a.txt"),
        "file-b": _fact("b", "b.txt"),
        "file-c": _fact("c", "c.txt"),
    }
    adapter.exact_results = {
        "a.txt": _fact("a", "a.txt"),
        "b.txt": _fact("b", "b.txt"),
        "c.txt": _fact("c", "c.txt"),
    }
    activities = tuple(
        _activity(100 + i, f"file-{v}", f"{v}.txt")
        for i, v in enumerate("abc", 1)
    )
    monkeypatch.setattr(
        service,
        "_fetch_activity_page",
        lambda c: _page(*activities, checkpoint="103"),
    )
    adapter.fail_exact_once.add("b.txt")
    with pytest.raises(RuntimeError, match="targeted DAV failed"):
        service.run_incremental()
    unchanged = states.read("nextcloud", NEXTCLOUD_INCREMENTAL_MECHANISM)
    assert unchanged.checkpoint == "100"
    first_a = repository.find_source("nextcloud", "a")
    service.run_incremental()
    assert states.read("nextcloud", NEXTCLOUD_INCREMENTAL_MECHANISM).checkpoint == "103"
    assert repository.find_source("nextcloud", "a").id == first_a.id
    assert {
        source.external_id
        for source in repository.list_active_sources("nextcloud")
    } == set("abc")


def test_gap_and_explicit_recovery(context, monkeypatch):
    adapter, _, states, _, service = context
    _checkpoint(states)
    monkeypatch.setattr(
        service, "_fetch_activity_page",
        lambda c: (_ for _ in ()).throw(InvalidCheckpointError("cursor gap")),
    )
    with pytest.raises(InvalidCheckpointError):
        service.run_incremental()
    required = states.read("nextcloud", NEXTCLOUD_INCREMENTAL_MECHANISM)
    assert required.checkpoint == "100" and required.reconciliation_required
    monkeypatch.setattr(service, "_capture_anchor", lambda: "500")
    adapter.full_facts = ()
    recovered = service.recover()
    assert recovered.checkpoint == "500"
    assert recovered.reconciliation_required is False


@pytest.mark.parametrize("anchor", ["500", "0"])
def test_bootstrap_installs_captured_anchor_last(context, monkeypatch, anchor):
    adapter, repository, states, _, service = context
    adapter.full_facts = (_fact("a", "a.txt"),)
    monkeypatch.setattr(service, "_capture_anchor", lambda: anchor)
    result = service.bootstrap()
    assert result.checkpoint == anchor
    assert repository.find_source("nextcloud", "a") is not None


def test_zero_anchor_first_activity_requires_full_recovery(context, monkeypatch):
    adapter, repository, states, engine, service = context
    adapter.full_facts = (_fact("a", "a.txt"), _fact("b", "b.txt"))
    engine.sync_once()
    _checkpoint(states, "0")
    monkeypatch.setattr(
        service,
        "_activity_request",
        lambda params: (
            SimpleNamespace(headers={
                "X-Activity-First-Known": "500",
                "X-Activity-Last-Given": "500",
            }),
            (_activity(500, "file-c", "c.txt"),),
        ),
    )

    with pytest.raises(InvalidCheckpointError, match="cannot prove continuity"):
        service.run_incremental()
    required = states.read("nextcloud", NEXTCLOUD_INCREMENTAL_MECHANISM)
    assert required.checkpoint == "0"
    assert required.reconciliation_required is True
    assert repository.find_source("nextcloud", "c") is None
    assert repository.find_source("nextcloud", "a").is_active is True
    assert repository.find_source("nextcloud", "b").is_active is True

    adapter.full_facts = (
        _fact("a", "a.txt"),
        _fact("b", "b.txt"),
        _fact("c", "c.txt"),
    )
    monkeypatch.setattr(service, "_capture_anchor", lambda: "500")
    recovered = service.recover()
    assert recovered.checkpoint == "500"
    assert recovered.reconciliation_required is False
    assert repository.find_source("nextcloud", "c") is not None


def test_empty_rendered_page_advances_provider_cursor_only(context, monkeypatch):
    adapter, repository, states, engine, service = context
    adapter.full_facts = (_fact("a", "a.txt"), _fact("b", "b.txt"))
    engine.sync_once()
    _checkpoint(states, "100")
    before = {
        source.external_id: source.id
        for source in repository.list_active_sources("nextcloud")
    }
    monkeypatch.setattr(
        service,
        "_activity_request",
        lambda params: (
            SimpleNamespace(
                status_code=304,
                headers={"X-Activity-Last-Given": "103"},
            ),
            (),
        ),
    )

    advanced = service.run_incremental()
    after = {
        source.external_id: source.id
        for source in repository.list_active_sources("nextcloud")
    }
    assert advanced.checkpoint == "103"
    assert advanced.reconciliation_required is False
    assert after == before
