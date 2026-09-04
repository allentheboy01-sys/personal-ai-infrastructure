from datetime import UTC, datetime

import pytest
import requests

from pdi.adapters.base import ProviderFact
from pdi.adapters.nextcloud import (
    ACTIVITY_PAGE_LIMIT,
    NEXTCLOUD_INCREMENTAL_MECHANISM,
    NextcloudActivityIncrementalSync,
    NextcloudActivityUnavailableError,
    NextcloudBootstrapRequiredError,
    decode_nextcloud_activity_checkpoint,
    encode_nextcloud_activity_checkpoint,
)
from pdi.engine import InvalidCheckpointError
from pdi.sync_state import ProviderSyncState


class _Response:
    def __init__(self, data=(), *, status=200, headers=None, error=None):
        self.status_code = status
        self.headers = headers or {}
        self._data = data
        self._error = error

    def raise_for_status(self):
        if self._error:
            raise self._error

    def json(self):
        return {"ocs": {"data": list(self._data)}}


class _Adapter:
    provider_name = "nextcloud"
    base_url = "https://nextcloud.example"
    username = "test-user"
    password = "test-password"

    def __init__(self):
        self.connected = 0
        self.search_results = {}
        self.exact_results = {}
        self.scanned = []

    def connect(self):
        self.connected += 1

    def search_by_fileid(self, file_id):
        return self.search_results.get(file_id)

    def propfind_exact(self, path):
        return self.exact_results.get(path)

    def scan(self, path=""):
        self.scanned.append(path)
        return ()


class _StateRepository:
    def __init__(self, checkpoint=None, *, required=False, version=0):
        now = datetime.now(UTC)
        self.state = ProviderSyncState(
            "nextcloud", NEXTCLOUD_INCREMENTAL_MECHANISM, checkpoint,
            version, required, now, now,
        )

    def get_or_create(self, provider, mechanism):
        return self.state

    def read(self, provider, mechanism):
        return self.state

    def compare_and_swap_checkpoint(
        self, provider, mechanism, *, expected_version, checkpoint
    ):
        if self.state.version != expected_version:
            return None
        now = datetime.now(UTC)
        self.state = ProviderSyncState(
            provider, mechanism, checkpoint, expected_version + 1,
            False, self.state.created_at, now,
        )
        return self.state

    def mark_reconciliation_required(
        self, provider, mechanism, *, expected_version
    ):
        if self.state.version != expected_version:
            return None
        now = datetime.now(UTC)
        self.state = ProviderSyncState(
            provider, mechanism, self.state.checkpoint, expected_version + 1,
            True, self.state.created_at, now,
        )
        return self.state

    def recover_after_reconciliation(
        self, provider, mechanism, *, expected_version, trusted_checkpoint
    ):
        if self.state.version != expected_version:
            return None
        now = datetime.now(UTC)
        self.state = ProviderSyncState(
            provider, mechanism, trusted_checkpoint, expected_version + 1,
            False, self.state.created_at, now,
        )
        return self.state


class _Engine:
    def __init__(self, states):
        self.states = states
        self.full_calls = 0
        self.batch = None

    def sync_once(self):
        self.full_calls += 1

    def sync_incremental(self, mechanism, discover):
        self.batch = discover(self.states.state)
        tuple(self.batch.facts)
        return self.states.compare_and_swap_checkpoint(
            "nextcloud", mechanism,
            expected_version=self.states.state.version,
            checkpoint=self.batch.next_checkpoint,
        )


def _activity(activity_id, **values):
    return {"activity_id": activity_id, **values}


def _fact(path, external_id="oc-id", *, folder=False):
    return ProviderFact(
        provider="nextcloud", kind="folder" if folder else "file",
        external_id=external_id, name=path.split("/")[-1],
        attributes={"path": path}, raw={"file_id": "123"},
    )


@pytest.mark.parametrize("value", [0, 1, 123456])
def test_activity_checkpoint_codec(value):
    assert decode_nextcloud_activity_checkpoint(
        encode_nextcloud_activity_checkpoint(value)
    ) == value


@pytest.mark.parametrize(
    "value", ["", "-1", "+1", "1.2", "abc", " 1", "1 ", "01", True, 1]
)
def test_activity_checkpoint_rejects_noncanonical_values(value):
    with pytest.raises(InvalidCheckpointError):
        decode_nextcloud_activity_checkpoint(value)


def test_null_checkpoint_requires_bootstrap_without_state_change():
    states = _StateRepository()
    service = NextcloudActivityIncrementalSync(
        _Adapter(), _Engine(states), states
    )
    with pytest.raises(NextcloudBootstrapRequiredError):
        service.run_incremental()
    assert states.state.checkpoint is None
    assert states.state.version == 0
    assert states.state.reconciliation_required is False


def test_activity_request_is_one_bounded_page(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda url, **kwargs: calls.append((url, kwargs)) or _Response(
            [_activity(101), _activity(102)],
            headers={"X-Activity-Last-Given": "102"},
        ),
    )
    states = _StateRepository("100")
    service = NextcloudActivityIncrementalSync(
        _Adapter(), _Engine(states), states
    )
    result = service.run_incremental()
    assert result.checkpoint == "102"
    assert len(calls) == 1
    assert calls[0][1]["params"] == {
        "sort": "asc", "since": 100, "limit": ACTIVITY_PAGE_LIMIT
    }
    assert calls[0][1]["headers"] == {
        "OCS-APIRequest": "true", "Accept": "application/json"
    }


def test_304_without_last_given_does_not_advance_version(monkeypatch):
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response(status=304),
    )
    states = _StateRepository("100", version=4)
    result = NextcloudActivityIncrementalSync(
        _Adapter(), _Engine(states), states
    ).run_incremental()
    assert result.version == 4
    assert result.checkpoint == "100"


def test_304_with_last_given_advances_empty_batch(monkeypatch):
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response(
            status=304, headers={"X-Activity-Last-Given": "103"}
        ),
    )
    states = _StateRepository("100", version=4)
    engine = _Engine(states)
    result = NextcloudActivityIncrementalSync(
        _Adapter(), engine, states
    ).run_incremental()
    assert result.checkpoint == "103"
    assert result.version == 5
    assert result.reconciliation_required is False
    assert tuple(engine.batch.facts) == ()


def test_304_first_known_invalidates_real_cursor(monkeypatch):
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response(
            status=304,
            headers={
                "X-Activity-First-Known": "200",
                "X-Activity-Last-Given": "203",
            },
        ),
    )
    states = _StateRepository("100")
    with pytest.raises(InvalidCheckpointError, match="cursor is unknown"):
        NextcloudActivityIncrementalSync(
            _Adapter(), _Engine(states), states
        ).run_incremental()
    assert states.state.checkpoint == "100"
    assert states.state.reconciliation_required is True


@pytest.mark.parametrize("status", [204, 404])
def test_activity_unavailable_does_not_change_state(monkeypatch, status):
    error = requests.HTTPError("unavailable") if status == 404 else None
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response(status=status, error=error),
    )
    states = _StateRepository("100", version=2)
    with pytest.raises(NextcloudActivityUnavailableError):
        NextcloudActivityIncrementalSync(
            _Adapter(), _Engine(states), states
        ).run_incremental()
    assert states.state.version == 2
    assert states.state.reconciliation_required is False


@pytest.mark.parametrize("first_known", [150, 50])
def test_first_known_presence_marks_reconciliation_required(
    monkeypatch, first_known
):
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response(
            [_activity(150)], headers={
                "X-Activity-First-Known": str(first_known),
                "X-Activity-Last-Given": "150",
            }
        ),
    )
    states = _StateRepository("100")
    with pytest.raises(InvalidCheckpointError, match="cursor is unknown"):
        NextcloudActivityIncrementalSync(
            _Adapter(), _Engine(states), states
        ).run_incremental()
    assert states.state.checkpoint == "100"
    assert states.state.reconciliation_required is True


def test_zero_checkpoint_first_activity_requires_reconciliation(monkeypatch):
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response(
            [_activity(500)], headers={
                "X-Activity-First-Known": "500",
                "X-Activity-Last-Given": "500",
            }
        ),
    )
    states = _StateRepository("0")
    adapter = _Adapter()
    with pytest.raises(InvalidCheckpointError, match="cannot prove continuity"):
        NextcloudActivityIncrementalSync(
            adapter, _Engine(states), states
        ).run_incremental()
    assert adapter.search_results == {}
    assert adapter.exact_results == {}
    assert adapter.scanned == []
    assert states.state.checkpoint == "0"
    assert states.state.reconciliation_required is True


def test_zero_checkpoint_empty_stream_is_unchanged(monkeypatch):
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response(status=304),
    )
    states = _StateRepository("0", version=4)
    result = NextcloudActivityIncrementalSync(
        _Adapter(), _Engine(states), states
    ).run_incremental()
    assert result.checkpoint == "0"
    assert result.version == 4
    assert result.reconciliation_required is False


def test_zero_checkpoint_304_first_known_without_cursor_is_noop(monkeypatch):
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response(
            status=304, headers={"X-Activity-First-Known": "500"}
        ),
    )
    states = _StateRepository("0", version=4)
    result = NextcloudActivityIncrementalSync(
        _Adapter(), _Engine(states), states
    ).run_incremental()
    assert result.checkpoint == "0"
    assert result.version == 4
    assert result.reconciliation_required is False


def test_zero_checkpoint_304_with_cursor_requires_recovery(monkeypatch):
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response(
            status=304, headers={"X-Activity-Last-Given": "500"}
        ),
    )
    states = _StateRepository("0")
    with pytest.raises(InvalidCheckpointError, match="cannot prove continuity"):
        NextcloudActivityIncrementalSync(
            _Adapter(), _Engine(states), states
        ).run_incremental()
    assert states.state.checkpoint == "0"
    assert states.state.reconciliation_required is True


@pytest.mark.parametrize("last_given", [100, 99])
def test_nonempty_page_cursor_must_advance(monkeypatch, last_given):
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response(
            [_activity(last_given)],
            headers={"X-Activity-Last-Given": str(last_given)},
        ),
    )
    states = _StateRepository("100")
    with pytest.raises(InvalidCheckpointError, match="did not advance"):
        NextcloudActivityIncrementalSync(
            _Adapter(), _Engine(states), states
        ).run_incremental()
    assert states.state.checkpoint == "100"
    assert states.state.reconciliation_required is True


@pytest.mark.parametrize("last", ["bad", None])
def test_last_given_must_be_present_and_canonical(monkeypatch, last):
    headers = {} if last is None else {"X-Activity-Last-Given": last}
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response([_activity(101)], headers=headers),
    )
    states = _StateRepository("100")
    with pytest.raises(ValueError):
        NextcloudActivityIncrementalSync(
            _Adapter(), _Engine(states), states
        ).run_incremental()
    assert states.state.checkpoint == "100"


@pytest.mark.parametrize(
    ("activity_ids", "last_given"),
    [([101, 102], 103), ([150], 120)],
)
def test_provider_cursor_is_independent_of_rendered_activity_ids(
    monkeypatch, activity_ids, last_given
):
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response(
            [_activity(value) for value in activity_ids],
            headers={"X-Activity-Last-Given": str(last_given)},
        ),
    )
    states = _StateRepository("100")
    result = NextcloudActivityIncrementalSync(
        _Adapter(), _Engine(states), states
    ).run_incremental()
    assert result.checkpoint == str(last_given)


def test_anchor_latest_and_empty_stream(monkeypatch):
    responses = iter([
        _Response([_activity(500)], headers={"X-Activity-Last-Given": "500"}),
        _Response([]),
    ])
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: next(responses),
    )
    states = _StateRepository()
    service = NextcloudActivityIncrementalSync(_Adapter(), _Engine(states), states)
    assert service._capture_anchor() == "500"
    assert service._capture_anchor() == "0"


def test_anchor_uses_last_given_from_304(monkeypatch):
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response(
            status=304, headers={"X-Activity-Last-Given": "500"}
        ),
    )
    states = _StateRepository()
    service = NextcloudActivityIncrementalSync(
        _Adapter(), _Engine(states), states
    )
    assert service.bootstrap().checkpoint == "500"


def test_bootstrap_and_recovery_install_anchor_only_after_full(monkeypatch):
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response(
            [_activity(500)], headers={"X-Activity-Last-Given": "500"}
        ),
    )
    states = _StateRepository()
    engine = _Engine(states)
    service = NextcloudActivityIncrementalSync(_Adapter(), engine, states)
    bootstrapped = service.bootstrap()
    assert engine.full_calls == 1
    assert bootstrapped.checkpoint == "500"

    states.mark_reconciliation_required(
        "nextcloud", NEXTCLOUD_INCREMENTAL_MECHANISM,
        expected_version=bootstrapped.version,
    )
    recovered = service.recover()
    assert engine.full_calls == 2
    assert recovered.checkpoint == "500"
    assert recovered.reconciliation_required is False


def test_full_failure_preserves_bootstrap_and_recovery_state(monkeypatch):
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response([]),
    )
    states = _StateRepository()
    engine = _Engine(states)
    engine.sync_once = lambda: (_ for _ in ()).throw(RuntimeError("full failed"))
    service = NextcloudActivityIncrementalSync(_Adapter(), engine, states)
    with pytest.raises(RuntimeError, match="full failed"):
        service.bootstrap()
    assert states.state.checkpoint is None and states.state.version == 0

    states.state = _StateRepository("old", required=True, version=3).state
    with pytest.raises(RuntimeError, match="full failed"):
        service.recover()
    assert states.state.checkpoint == "old"
    assert states.state.reconciliation_required is True


def test_ordinary_http_failure_does_not_mark_checkpoint_invalid(monkeypatch):
    monkeypatch.setattr(
        "pdi.adapters.nextcloud.incremental.requests.get",
        lambda *args, **kwargs: _Response(
            status=500, error=requests.HTTPError("server failed")
        ),
    )
    states = _StateRepository("100", version=2)
    with pytest.raises(requests.HTTPError):
        NextcloudActivityIncrementalSync(
            _Adapter(), _Engine(states), states
        ).run_incremental()
    assert states.state.checkpoint == "100"
    assert states.state.version == 2
    assert states.state.reconciliation_required is False


def test_candidates_ignore_non_files_support_objects_and_deduplicate():
    adapter = _Adapter()
    states = _StateRepository("100")
    service = NextcloudActivityIncrementalSync(adapter, _Engine(states), states)
    assert service._candidates(_activity(1, object_type="calendar")) == ()
    activities = (
        _activity(2, object_type="files", objects={"123": "/A.txt", "124": "/B.txt"}),
        _activity(3, object_type="files", object_id=123, object_name="/old.txt"),
    )
    adapter.exact_results = {
        "A.txt": _fact("A.txt", "a"),
        "B.txt": _fact("B.txt", "b"),
    }
    assert [
        fact.external_id for fact in service._revalidate_activities(activities)
    ] == ["a", "b"]


def test_search_path_wins_for_rename_and_folder_scans_subtree():
    adapter = _Adapter()
    states = _StateRepository("100")
    service = NextcloudActivityIncrementalSync(adapter, _Engine(states), states)
    adapter.search_results["123"] = _fact("new/name.txt")
    adapter.exact_results["new/name.txt"] = _fact("new/name.txt", "same-id")
    facts = tuple(service._revalidate_activities((
        _activity(101, object_type="files", object_id=123, object_name="old/name.txt"),
    )))
    assert facts[0].attributes["path"] == "new/name.txt"

    adapter.search_results["500"] = _fact("B", "folder", folder=True)
    adapter.exact_results["B"] = _fact("B", "folder", folder=True)
    tuple(service._revalidate_activities((
        _activity(102, object_type="files", object_id=500, object_name="A"),
    )))
    assert adapter.scanned == ["B"]


@pytest.mark.parametrize("path", ["../secret", "A/./file", "/", ""])
def test_invalid_or_root_path_does_not_escape_scope(path):
    service = NextcloudActivityIncrementalSync(
        _Adapter(), _Engine(_StateRepository("1")), _StateRepository("1")
    )
    if "." in path:
        with pytest.raises(ValueError):
            service._path_hint(path)
    else:
        assert service._path_hint(path) is None
