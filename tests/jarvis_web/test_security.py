import pytest
from starlette.requests import Request

from jarvis.web import TailscaleServeAuth
from jarvis.web.auth import AuthenticationError

pytestmark = pytest.mark.anyio

ORIGIN = "https://jarvis.test"
WRITE_HEADERS = {"Origin": ORIGIN, "X-Jarvis-Request": "web-v1", "Content-Type": "application/json"}


async def test_csrf_rejections_and_security_headers(client) -> None:
    assert (await client.post("/api/v1/conversations", json={})).status_code == 403
    assert (await client.post("/api/v1/conversations", headers={"Origin": "https://foreign.test", "X-Jarvis-Request": "web-v1"}, json={})).status_code == 403
    assert (await client.post("/api/v1/conversations", headers={"Origin": ORIGIN, "X-Jarvis-Request": "web-v1", "Content-Type": "text/plain"}, content="{}")).status_code == 403
    assert (await client.post("/api/v1/conversations", headers={"Origin": ORIGIN}, json={})).status_code == 403
    accepted = await client.post("/api/v1/conversations", headers=WRITE_HEADERS, json={})
    assert accepted.status_code == 201
    assert accepted.headers["cache-control"] == "private, no-store"
    assert accepted.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in accepted.headers["content-security-policy"]


def _request(client_host: str, headers: list[tuple[bytes, bytes]]) -> Request:
    return Request({"type": "http", "http_version": "1.1", "method": "GET", "scheme": "https", "path": "/", "raw_path": b"/", "query_string": b"", "headers": headers, "client": (client_host, 1234), "server": ("jarvis", 443)})


async def test_tailscale_adapter_requires_localhost_and_exact_login() -> None:
    auth = TailscaleServeAuth(frozenset({"allowed@example.test"}))
    principal = await auth.authenticate(_request("127.0.0.1", [(b"tailscale-user-login", b"allowed@example.test")]))
    assert principal.subject == "allowed@example.test"
    for request in (_request("10.0.0.2", [(b"tailscale-user-login", b"allowed@example.test")]), _request("127.0.0.1", []), _request("127.0.0.1", [(b"tailscale-user-login", b"other@example.test")])):
        try:
            await auth.authenticate(request)
        except AuthenticationError:
            pass
        else:
            raise AssertionError("request should be rejected")


async def test_sse_get_is_read_only_and_needs_no_csrf_header(client) -> None:
    conversation = (await client.post("/api/v1/conversations", headers=WRITE_HEADERS, json={})).json()["id"]
    turn = (await client.post(f"/api/v1/conversations/{conversation}/turns", headers=WRITE_HEADERS, json={"body": "hello"})).json()["turn_id"]
    response = await client.get(f"/api/v1/turns/{turn}/events")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
