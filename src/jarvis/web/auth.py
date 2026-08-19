from dataclasses import dataclass
from typing import Protocol

from starlette.requests import Request


@dataclass(frozen=True, slots=True)
class JarvisPrincipal:
    subject: str


class AuthenticationError(Exception):
    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


class AuthAdapter(Protocol):
    async def authenticate(self, request: Request) -> JarvisPrincipal: ...


class TestAuthAdapter:
    def __init__(self, subject: str = "test-user") -> None:
        self._principal = JarvisPrincipal(subject)

    async def authenticate(self, request: Request) -> JarvisPrincipal:
        return self._principal


class TailscaleServeAuth:
    def __init__(self, allowed_logins: frozenset[str]) -> None:
        if not allowed_logins:
            raise ValueError("at least one Tailscale login is required")
        self._allowed_logins = allowed_logins

    async def authenticate(self, request: Request) -> JarvisPrincipal:
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1"}:
            raise AuthenticationError(401, "untrusted_proxy_boundary")
        login = request.headers.get("Tailscale-User-Login")
        if login is None:
            raise AuthenticationError(401, "identity_missing")
        if login not in self._allowed_logins:
            raise AuthenticationError(403, "identity_not_allowed")
        return JarvisPrincipal(login)
