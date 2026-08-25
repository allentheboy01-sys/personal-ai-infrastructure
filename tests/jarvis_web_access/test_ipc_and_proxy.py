import asyncio
import json
from pathlib import Path

from jarvis.web_access.contract import MAX_TOOL_RESULT_CHARS
from jarvis.web_access.ipc import WebAccessIpcServer
from jarvis.web_access.service import _bound_result
from jarvis.web_proxy.main import TurnBudget, UnixIpcClient, create_server


class FakeService:
    async def search(self, query, limit=5):
        return {"ok": True, "results": [{"title": query, "limit": limit}]}

    async def fetch(self, url):
        return {"ok": True, "final_url": url, "content_trust": "untrusted_web"}


def test_private_unix_ipc_round_trip_has_no_tcp_listener(tmp_path: Path) -> None:
    async def run() -> None:
        path = tmp_path / "web.sock"
        server = await asyncio.start_unix_server(WebAccessIpcServer(FakeService()).handle, path=path)  # type: ignore[arg-type]
        async with server:
            client = UnixIpcClient(str(path))
            result = await client.request({"version": 1, "operation": "search", "query": "q", "limit": 2})
            assert result == {"ok": True, "results": [{"title": "q", "limit": 2}]}
            invalid = await client.request({"version": 1, "operation": "fetch", "url": "https://x", "headers": {}})
            assert invalid == {"ok": False, "error": "invalid_request"}
        assert not path.exists()

    asyncio.run(run())


class RecordingClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []
        self.active = 0
        self.maximum = 0

    async def request(self, value: dict[str, object]) -> dict[str, object]:
        self.requests.append(value)
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return {"ok": True}


def test_mcp_exposes_exact_narrow_schemas() -> None:
    async def run():
        return await create_server(RecordingClient()).list_tools()

    tools = asyncio.run(run())
    assert [tool.name for tool in tools] == ["jarvis_web_search", "jarvis_web_fetch"]
    search, fetch = tools
    assert search.input_schema["properties"]["query"] == {"maxLength": 400, "minLength": 1, "title": "Query", "type": "string"}
    assert search.input_schema["properties"]["limit"]["minimum"] == 1
    assert search.input_schema["properties"]["limit"]["maximum"] == 5
    assert fetch.input_schema["properties"]["url"]["maxLength"] == 2048
    serialized = repr(tools)
    for forbidden in ("headers", "method", "body", "proxy", "cookie", "authorization", "redirect"):
        assert forbidden not in serialized.lower()


def test_actual_mcp_text_serialization_stays_under_tool_result_bound() -> None:
    class BoundedClient:
        async def request(self, _value: dict[str, object]) -> dict[str, object]:
            return _bound_result(
                {
                    "ok": True,
                    "requested_url": "https://example.com/" + "a" * 2_000,
                    "final_url": "https://example.com/" + "b" * 2_000,
                    "title": "title",
                    "mime": "text/plain",
                    "content": "x" * 20_000,
                    "retrieved_at": "2026-08-25T00:00:00+00:00",
                    "truncated": False,
                    "content_trust": "untrusted_web",
                }
            )

    result = asyncio.run(
        create_server(BoundedClient()).call_tool("jarvis_web_fetch", {"url": "https://example.com/"})
    )
    assert len(result.content[0].text) <= MAX_TOOL_RESULT_CHARS
    assert len(json.dumps(result.structured_content, ensure_ascii=False, indent=2)) <= MAX_TOOL_RESULT_CHARS


def test_turn_search_and_fetch_budgets_and_isolation() -> None:
    async def run() -> None:
        first_client = RecordingClient()
        first = create_server(first_client)
        assert (await first.call_tool("jarvis_web_search", {"query": "a"})).structured_content["ok"] is True
        assert (await first.call_tool("jarvis_web_search", {"query": "b"})).structured_content["ok"] is True
        blocked_search = await first.call_tool("jarvis_web_search", {"query": "c"})
        assert blocked_search.structured_content == {"ok": False, "error": "turn_budget_exceeded"}
        for index in range(3):
            result = await first.call_tool("jarvis_web_fetch", {"url": f"https://example.com/{index}"})
            assert result.structured_content["ok"] is True
        blocked_fetch = await first.call_tool("jarvis_web_fetch", {"url": "https://example.com/3"})
        assert blocked_fetch.structured_content == {"ok": False, "error": "turn_budget_exceeded"}
        assert len(first_client.requests) == 5

        second_client = RecordingClient()
        second = create_server(second_client)
        assert (await second.call_tool("jarvis_web_search", {"query": "new turn"})).structured_content["ok"] is True
        assert (await second.call_tool("jarvis_web_fetch", {"url": "https://example.com/new"})).structured_content["ok"] is True

    asyncio.run(run())


def test_equivalent_urls_share_distinct_url_budget_identity() -> None:
    async def run() -> None:
        budget = TurnBudget()
        assert await budget.reserve_fetch("HTTPS://Example.COM.:443/a#one")
        assert await budget.reserve_fetch("https://example.com/a#two")
        assert await budget.reserve_fetch("https://example.com/b")
        assert not await budget.reserve_fetch("https://example.com/c")  # fourth call and third new key after call bound

    asyncio.run(run())


def test_per_turn_fetch_concurrency_is_two() -> None:
    async def run() -> int:
        client = RecordingClient()
        server = create_server(client)
        await asyncio.gather(
            server.call_tool("jarvis_web_fetch", {"url": "https://example.com/a"}),
            server.call_tool("jarvis_web_fetch", {"url": "https://example.com/b"}),
            server.call_tool("jarvis_web_fetch", {"url": "https://example.com/c"}),
        )
        return client.maximum

    assert asyncio.run(run()) == 2
