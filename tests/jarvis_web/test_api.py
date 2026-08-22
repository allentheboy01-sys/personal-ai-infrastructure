import asyncio
import json
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from jarvis.runtime import (
    MockRuntimeAdapter,
    RuntimeCapability,
    RuntimeEvent,
    RuntimeEventType,
    RuntimeToolCategory,
)

pytestmark = pytest.mark.anyio

WRITE_HEADERS = {"Origin": "https://jarvis.test", "X-Jarvis-Request": "web-v1", "Content-Type": "application/json"}


class DelayedCancelRuntime(MockRuntimeAdapter):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cancel_tasks: set[asyncio.Task[None]] = set()

    async def cancel_turn(self, turn_id) -> None:
        session = self._sessions.get(turn_id)
        if session is None or session.cancel.is_set():
            return

        async def cancel_later() -> None:
            await asyncio.sleep(0.35)
            session.cancel.set()

        task = asyncio.create_task(cancel_later())
        self._cancel_tasks.add(task)
        task.add_done_callback(self._cancel_tasks.discard)


class ShutdownFailureRuntime:
    def __init__(self) -> None:
        self._queues = {}

    async def start_turn(self, context) -> None:
        queue = asyncio.Queue()
        self._queues[context.turn_id] = queue
        await queue.put(RuntimeEvent(context.turn_id, 1, RuntimeEventType.TURN_STARTED))

    async def cancel_turn(self, turn_id) -> None:
        await self._queues[turn_id].put(
            RuntimeEvent(turn_id, 2, RuntimeEventType.TURN_FAILED, error_code="bridge_nonzero_exit")
        )

    async def stream_events(self, turn_id):
        while True:
            event = await self._queues[turn_id].get()
            yield event
            if event.type in {RuntimeEventType.TURN_COMPLETED, RuntimeEventType.TURN_FAILED, RuntimeEventType.TURN_CANCELLED}:
                return


class ToolEventRuntime:
    def __init__(self) -> None:
        self._queues = {}

    async def start_turn(self, context) -> None:
        queue = asyncio.Queue()
        self._queues[context.turn_id] = queue
        events = (
            RuntimeEvent(context.turn_id, 1, RuntimeEventType.TURN_STARTED),
            RuntimeEvent(
                context.turn_id,
                2,
                RuntimeEventType.TOOL_STARTED,
                operation_id=1,
                category=RuntimeToolCategory.PDI,
                capability=RuntimeCapability.SEARCH_PERSONAL_RESOURCES,
            ),
            RuntimeEvent(
                context.turn_id,
                3,
                RuntimeEventType.TOOL_COMPLETED,
                operation_id=1,
                category=RuntimeToolCategory.PDI,
                capability=RuntimeCapability.SEARCH_PERSONAL_RESOURCES,
                duration_ms=18,
            ),
            RuntimeEvent(context.turn_id, 4, RuntimeEventType.MESSAGE_DELTA, delta="safe answer"),
            RuntimeEvent(context.turn_id, 5, RuntimeEventType.TURN_COMPLETED),
        )
        for event in events:
            await queue.put(event)

    async def cancel_turn(self, turn_id) -> None:
        return None

    async def stream_events(self, turn_id):
        while True:
            event = await self._queues[turn_id].get()
            yield event
            if event.type in {RuntimeEventType.TURN_COMPLETED, RuntimeEventType.TURN_FAILED, RuntimeEventType.TURN_CANCELLED}:
                return


async def _conversation(client):
    response = await client.post("/api/v1/conversations", headers=WRITE_HEADERS, json={"title": "Persistent chat"})
    assert response.status_code == 201
    return response.json()["id"]


async def _wait_terminal(client, turn_id: str):
    for _ in range(1000):
        payload = (await client.get(f"/api/v1/turns/{turn_id}")).json()
        if payload["status"] != "running":
            return payload
        await asyncio.sleep(0.005)
    raise AssertionError("turn did not finish")


async def test_create_list_get_and_refresh_canonical_history(client) -> None:
    conversation_id = await _conversation(client)
    turn = await client.post(f"/api/v1/conversations/{conversation_id}/turns", headers=WRITE_HEADERS, json={"body": "Hello"})
    assert turn.status_code == 201
    terminal = await _wait_terminal(client, turn.json()["turn_id"])
    assert terminal["status"] == "completed"

    detail = await client.get(f"/api/v1/conversations/{conversation_id}")
    assert detail.status_code == 200
    assert [(item["role"], item["body"]) for item in detail.json()["messages"]] == [("user", "Hello"), ("assistant", "I reviewed the available context. This is a deterministic mock response from the Jarvis runtime contract.")]
    assert any(item["id"] == conversation_id for item in (await client.get("/api/v1/conversations")).json())


async def test_sse_contract_and_replay(client) -> None:
    conversation_id = await _conversation(client)
    turn_id = (await client.post(f"/api/v1/conversations/{conversation_id}/turns", headers=WRITE_HEADERS, json={"body": "Hello"})).json()["turn_id"]
    response = await client.get(f"/api/v1/turns/{turn_id}/events")
    assert response.status_code == 200
    assert "event: turn.started" in response.text
    assert "event: message.delta" in response.text
    assert response.text.count("event: turn.completed") == 1
    replay = await client.get(f"/api/v1/turns/{turn_id}/events", headers={"Last-Event-ID": "3"})
    assert "id: 1\n" not in replay.text
    assert "event: turn.completed" in replay.text


async def test_sse_replays_only_sanitized_tool_metadata(app_factory) -> None:
    app = app_factory(ToolEventRuntime())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://jarvis.test") as client:
            conversation_id = await _conversation(client)
            turn_id = (
                await client.post(
                    f"/api/v1/conversations/{conversation_id}/turns",
                    headers=WRITE_HEADERS,
                    json={"body": "synthetic"},
                )
            ).json()["turn_id"]
            response = await client.get(f"/api/v1/turns/{turn_id}/events")
            replay = await client.get(f"/api/v1/turns/{turn_id}/events", headers={"Last-Event-ID": "1"})

    assert "event: tool.started" in response.text
    assert "event: tool.completed" in response.text
    tool_payloads = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ") and '"type":"tool.' in line
    ]
    assert tool_payloads == [
        {"turn_id": turn_id, "sequence": 2, "type": "tool.started", "operation_id": 1, "category": "pdi", "capability": "search_personal_resources"},
        {"turn_id": turn_id, "sequence": 3, "type": "tool.completed", "operation_id": 1, "category": "pdi", "capability": "search_personal_resources", "duration_ms": 18},
    ]
    assert "event: tool.started" in replay.text
    for forbidden in ("arguments", "result", "resource_ref", "filename", "path", "provider_id", "raw_tool"):
        assert forbidden not in response.text


async def test_cancel_and_failure_never_create_partial_assistant(app_factory) -> None:
    async def exercise(runtime: MockRuntimeAdapter, *, cancel: bool) -> None:
        app = app_factory(runtime)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="https://jarvis.test") as client:
                conversation = await _conversation(client)
                turn = (await client.post(f"/api/v1/conversations/{conversation}/turns", headers=WRITE_HEADERS, json={"body": "ordinary user text"})).json()["turn_id"]
                if cancel:
                    response = await client.post(f"/api/v1/turns/{turn}/cancel", headers=WRITE_HEADERS, json={})
                    assert response.json()["status"] == "cancelled"
                    assert (await client.post(f"/api/v1/turns/{turn}/cancel", headers=WRITE_HEADERS, json={})).json()["status"] == "cancelled"
                else:
                    assert (await _wait_terminal(client, turn))["status"] == "failed"
                assert [item["role"] for item in (await client.get(f"/api/v1/conversations/{conversation}")).json()["messages"]] == ["user"]

    await exercise(DelayedCancelRuntime(delay=1), cancel=True)
    await exercise(MockRuntimeAdapter(scenario="failure", delay=0), cancel=False)


async def test_lifespan_shutdown_interrupts_running_turn_before_runtime_cleanup(app_factory) -> None:
    app = app_factory(ShutdownFailureRuntime())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://jarvis.test") as client:
            conversation = await _conversation(client)
            turn_id = (
                await client.post(
                    f"/api/v1/conversations/{conversation}/turns",
                    headers=WRITE_HEADERS,
                    json={"body": "ordinary user text"},
                )
            ).json()["turn_id"]
            assert (await client.get(f"/api/v1/turns/{turn_id}")).json()["status"] == "running"

    turn = app.state.jarvis_state.get_turn(UUID(turn_id))
    assert turn.status == "interrupted"
    assert turn.error_code == "process_restarted"
    assert turn.assistant_message_id is None
    assert app.state.turn_coordinator._tasks == {}


async def test_not_found_boundaries(client) -> None:
    missing = uuid4()
    assert (await client.get(f"/api/v1/conversations/{missing}")).status_code == 404
    assert (await client.get(f"/api/v1/turns/{missing}")).status_code == 404
    assert (await client.post(f"/api/v1/turns/{missing}/cancel", headers=WRITE_HEADERS, json={})).status_code == 404
    conversation_id = await _conversation(client)
    assert (await client.post(f"/api/v1/conversations/{conversation_id}/turns", headers=WRITE_HEADERS, json={"body": "   "})).status_code == 422


async def test_same_origin_static_and_spa_fallback(client) -> None:
    index = await client.get("/")
    assert index.status_code == 200 and index.headers["cache-control"] == "private, no-cache"
    fallback = await client.get("/conversations/example")
    assert fallback.text.startswith("<!doctype html>") and fallback.headers["cache-control"] == "private, no-cache"
    asset = await client.get("/app.js")
    assert asset.headers["content-type"].startswith("text/javascript")
    assert asset.headers["cache-control"] == "private, no-cache"
    immutable = await client.get("/assets/app-ABC123.js")
    assert immutable.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert (await client.get("/api/v1/unknown")).status_code == 404
