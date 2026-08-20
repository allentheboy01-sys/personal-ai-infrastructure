import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from jarvis.runtime import MockRuntimeAdapter

pytestmark = pytest.mark.anyio

WRITE_HEADERS = {"Origin": "https://jarvis.test", "X-Jarvis-Request": "web-v1", "Content-Type": "application/json"}


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

    await exercise(MockRuntimeAdapter(delay=0.2), cancel=True)
    await exercise(MockRuntimeAdapter(scenario="failure", delay=0), cancel=False)


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
