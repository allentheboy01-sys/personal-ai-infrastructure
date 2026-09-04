from dataclasses import dataclass
from typing import Any, Iterable
import urllib.parse

import requests

from pdi.adapters.base import ProviderFact
from pdi.engine import (
    CheckpointCASConflictError,
    DiscoveryBatch,
    DiscoveryMode,
    InvalidCheckpointError,
    ReconciliationRequiredError,
    SyncEngine,
)
from pdi.sync_state import ProviderSyncState, ProviderSyncStateRepository

from .adapter import NextcloudAdapter


NEXTCLOUD_INCREMENTAL_MECHANISM = "activity_v2_hint_v1"
ACTIVITY_ENDPOINT = "/ocs/v2.php/apps/activity/api/v2/activity/all"
ACTIVITY_PAGE_LIMIT = 200


class NextcloudBootstrapRequiredError(RuntimeError):
    """No trusted Nextcloud Activity checkpoint exists."""


class NextcloudActivityUnavailableError(RuntimeError):
    """The configured account cannot use the Activity hint mechanism."""


class NextcloudTargetResolutionError(RuntimeError):
    """A file hint could not be resolved unambiguously."""


def encode_nextcloud_activity_checkpoint(value: int) -> str:
    if type(value) is not int or value < 0:
        raise InvalidCheckpointError("Activity checkpoint must be non-negative")
    return str(value)


def decode_nextcloud_activity_checkpoint(value: str) -> int:
    if (
        not isinstance(value, str)
        or not value
        or not value.isdecimal()
        or str(int(value)) != value
    ):
        raise InvalidCheckpointError("Malformed Nextcloud Activity checkpoint")
    return int(value)


@dataclass(frozen=True, slots=True)
class ActivityCandidate:
    file_id: str | None
    path: str | None


@dataclass(frozen=True, slots=True)
class ActivityPage:
    activities: tuple[dict[str, Any], ...]
    next_checkpoint: str | None
    no_activity: bool = False


class NextcloudActivityIncrementalSync:
    def __init__(
        self,
        adapter: NextcloudAdapter,
        engine: SyncEngine,
        state_repository: ProviderSyncStateRepository,
    ) -> None:
        self.adapter = adapter
        self.engine = engine
        self.state_repository = state_repository

    def run_incremental(self) -> ProviderSyncState:
        state = self.state_repository.get_or_create(
            self.adapter.provider_name, NEXTCLOUD_INCREMENTAL_MECHANISM
        )
        if state.reconciliation_required:
            raise ReconciliationRequiredError(
                "Nextcloud Activity state requires explicit recovery"
            )
        if state.checkpoint is None:
            raise NextcloudBootstrapRequiredError(
                "Nextcloud Activity incremental sync requires bootstrap"
            )
        checkpoint = decode_nextcloud_activity_checkpoint(state.checkpoint)
        self.adapter.connect()
        try:
            page = self._fetch_activity_page(checkpoint)
        except InvalidCheckpointError:
            marked = self.state_repository.mark_reconciliation_required(
                state.provider,
                state.mechanism,
                expected_version=state.version,
            )
            if marked is None:
                raise CheckpointCASConflictError(
                    "Nextcloud Activity state changed while marking a gap"
                ) from None
            raise
        if page.no_activity:
            return state

        return self.engine.sync_incremental(
            NEXTCLOUD_INCREMENTAL_MECHANISM,
            lambda current: DiscoveryBatch(
                provider=self.adapter.provider_name,
                mode=DiscoveryMode.INCREMENTAL_NON_AUTHORITATIVE,
                facts=self._revalidate_activities(page.activities),
                next_checkpoint=page.next_checkpoint,
            ),
        )

    def bootstrap(self) -> ProviderSyncState:
        state = self.state_repository.get_or_create(
            self.adapter.provider_name, NEXTCLOUD_INCREMENTAL_MECHANISM
        )
        if state.reconciliation_required or state.checkpoint is not None:
            raise RuntimeError("Nextcloud bootstrap requires uninitialized state")
        self.adapter.connect()
        anchor = self._capture_anchor()
        self.engine.sync_once()
        advanced = self.state_repository.compare_and_swap_checkpoint(
            state.provider,
            state.mechanism,
            expected_version=state.version,
            checkpoint=anchor,
        )
        if advanced is None:
            raise CheckpointCASConflictError(
                "Nextcloud bootstrap checkpoint CAS failed"
            )
        return advanced

    def recover(self) -> ProviderSyncState:
        state = self.state_repository.get_or_create(
            self.adapter.provider_name, NEXTCLOUD_INCREMENTAL_MECHANISM
        )
        if not state.reconciliation_required:
            raise RuntimeError("Nextcloud recovery requires reconciliation state")
        self.adapter.connect()
        anchor = self._capture_anchor()
        self.engine.sync_once()
        recovered = self.state_repository.recover_after_reconciliation(
            state.provider,
            state.mechanism,
            expected_version=state.version,
            trusted_checkpoint=anchor,
        )
        if recovered is None:
            raise CheckpointCASConflictError("Nextcloud recovery checkpoint CAS failed")
        return recovered

    def _activity_request(self, params: dict[str, object]):
        response = requests.get(
            f"{self.adapter.base_url}{ACTIVITY_ENDPOINT}",
            headers={
                "OCS-APIRequest": "true",
                "Accept": "application/json",
            },
            auth=(self.adapter.username, self.adapter.password),
            params=params,
            timeout=30,
        )
        if response.status_code == 204:
            raise NextcloudActivityUnavailableError(
                "Nextcloud Activity API is unavailable"
            )
        if response.status_code == 304:
            return response, ()
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            if response.status_code == 404:
                raise NextcloudActivityUnavailableError(
                    "Nextcloud Activity API is unavailable"
                ) from error
            raise
        payload = response.json()
        try:
            data = payload["ocs"]["data"]
        except (KeyError, TypeError) as error:
            raise ValueError("Malformed Nextcloud Activity response") from error
        if not isinstance(data, list) or not all(
            isinstance(value, dict) for value in data
        ):
            raise ValueError("Malformed Nextcloud Activity data")
        return response, tuple(data)

    def _fetch_activity_page(self, checkpoint: int) -> ActivityPage:
        response, activities = self._activity_request({
            "sort": "asc",
            "since": checkpoint,
            "limit": ACTIVITY_PAGE_LIMIT,
        })
        first_known = self._header_int(response, "X-Activity-First-Known", False)
        if checkpoint > 0 and first_known is not None:
            raise InvalidCheckpointError("Nextcloud Activity cursor is unknown")
        last_given = self._header_int(
            response, "X-Activity-Last-Given", False
        )
        if getattr(response, "status_code", 200) == 304:
            if last_given is None:
                return ActivityPage((), None, no_activity=True)
            if checkpoint == 0:
                raise InvalidCheckpointError(
                    "Nextcloud synthetic zero Activity anchor cannot prove continuity"
                )
            self._validate_cursor_advance(checkpoint, last_given)
            return ActivityPage(
                (), encode_nextcloud_activity_checkpoint(last_given)
            )
        if not activities:
            return ActivityPage((), None, no_activity=True)
        if checkpoint == 0:
            raise InvalidCheckpointError(
                "Nextcloud synthetic zero Activity anchor cannot prove continuity"
            )
        for activity in activities:
            self._activity_id(activity)
        if last_given is None:
            raise ValueError("Missing Nextcloud Activity continuation cursor")
        self._validate_cursor_advance(checkpoint, last_given)
        return ActivityPage(
            activities, encode_nextcloud_activity_checkpoint(last_given)
        )

    def _capture_anchor(self) -> str:
        response, activities = self._activity_request({"sort": "desc", "limit": 1})
        for activity in activities:
            self._activity_id(activity)
        last_given = self._header_int(
            response, "X-Activity-Last-Given", bool(activities)
        )
        if last_given is None:
            return "0"
        if last_given <= 0:
            raise ValueError("Nextcloud Activity anchor cursor must be positive")
        return encode_nextcloud_activity_checkpoint(last_given)

    @staticmethod
    def _validate_cursor_advance(checkpoint: int, last_given: int) -> None:
        if last_given <= checkpoint:
            raise InvalidCheckpointError(
                "Nextcloud Activity continuation cursor did not advance"
            )

    @staticmethod
    def _header_int(response, name: str, required: bool) -> int | None:
        value = next(
            (v for k, v in response.headers.items() if k.lower() == name.lower()),
            None,
        )
        if value is None and not required:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Malformed Nextcloud Activity header: {name}") from error
        if str(parsed) != str(value):
            raise ValueError(f"Malformed Nextcloud Activity header: {name}")
        return parsed

    @staticmethod
    def _activity_id(activity: dict[str, Any]) -> int:
        value = activity.get("activity_id")
        if type(value) is not int or value <= 0:
            raise ValueError("Malformed Nextcloud activity_id")
        return value

    def _revalidate_activities(
        self, activities: tuple[dict[str, Any], ...]
    ) -> Iterable[ProviderFact]:
        seen_candidates: set[tuple[str, str]] = set()
        seen_external_ids: set[str] = set()
        for activity in activities:
            for candidate in self._candidates(activity):
                key = (
                    ("fileid", candidate.file_id)
                    if candidate.file_id is not None
                    else ("path", candidate.path or "")
                )
                if key in seen_candidates:
                    continue
                seen_candidates.add(key)
                fact = self._resolve_candidate(candidate)
                if fact is None:
                    continue
                facts = (
                    self.adapter.scan(fact.attributes["path"])
                    if fact.kind == "folder"
                    else (fact,)
                )
                for resolved in facts:
                    if resolved.external_id in seen_external_ids:
                        continue
                    if resolved.external_id is not None:
                        seen_external_ids.add(resolved.external_id)
                    yield resolved

    def _resolve_candidate(
        self, candidate: ActivityCandidate
    ) -> ProviderFact | None:
        located = None
        if candidate.file_id is not None:
            try:
                located = self.adapter.search_by_fileid(candidate.file_id)
            except ValueError as error:
                raise NextcloudTargetResolutionError(str(error)) from error
        path = (
            located.attributes.get("path") if located is not None else candidate.path
        )
        if not isinstance(path, str) or not path:
            return None
        for _ in range(2):
            fact = self.adapter.propfind_exact(path)
            if fact is not None:
                return fact
        return None

    def _candidates(self, activity: dict[str, Any]) -> tuple[ActivityCandidate, ...]:
        if activity.get("object_type") != "files":
            return ()
        candidates: list[ActivityCandidate] = []
        objects = activity.get("objects")
        if isinstance(objects, dict):
            for file_id, path in objects.items():
                candidates.append(
                    ActivityCandidate(str(file_id), self._path_hint(path))
                )
        file_id = activity.get("object_id")
        path = self._path_hint(activity.get("object_name"))
        if file_id is not None or path is not None:
            candidates.append(
                ActivityCandidate(str(file_id) if file_id is not None else None, path)
            )
        return tuple(candidates)

    @staticmethod
    def _path_hint(value: object) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        decoded = urllib.parse.unquote(value).strip("/")
        segments = [segment for segment in decoded.split("/") if segment]
        if not segments:
            return None
        if any(segment in {".", ".."} for segment in segments):
            raise ValueError("Invalid Nextcloud Activity path hint")
        return "/".join(segments)
