from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from .auth import AuthAdapter, AuthenticationError


CSP = "default-src 'self'; script-src 'self'; style-src-elem 'self'; style-src-attr 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; worker-src 'none'"


class BrowserSecurityMiddleware:
    def __init__(self, app: ASGIApp, *, auth_adapter: AuthAdapter, allowed_origin: str) -> None:
        self.app = app
        self._auth = auth_adapter
        self._origin = allowed_origin

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        try:
            request.state.principal = await self._auth.authenticate(request)
        except AuthenticationError as error:
            await self._respond(JSONResponse({"detail": error.code}, status_code=error.status_code), scope, receive, send)
            return
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/"):
            rejection = self._csrf_rejection(request)
            if rejection is not None:
                await self._respond(JSONResponse({"detail": rejection}, status_code=403), scope, receive, send)
                return
        await self.app(scope, receive, self._security_send(send, request.url.path))

    def _csrf_rejection(self, request: Request) -> str | None:
        if request.headers.get("origin") != self._origin:
            return "origin_rejected"
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return "content_type_rejected"
        if request.headers.get("X-Jarvis-Request") != "web-v1":
            return "request_header_rejected"
        return None

    @staticmethod
    def _security_send(send: Send, path: str) -> Callable[[dict], Awaitable[None]]:
        async def wrapped(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"content-security-policy", CSP.encode("ascii")),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
                ])
                if path.startswith("/api/"):
                    headers = [(name, value) for name, value in headers if name.lower() != b"cache-control"]
                    headers.append((b"cache-control", b"private, no-store"))
                message["headers"] = headers
            await send(message)
        return wrapped

    async def _respond(self, response: Response, scope: Scope, receive: Receive, send: Send) -> None:
        await response(scope, receive, self._security_send(send, scope.get("path", "")))
