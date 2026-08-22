# Jarvis Web UI V0.1 — Stage 2 State and FastAPI Skeleton

## Status

FROZEN

2026-08-19

## Boundary

Stage 2 adds a Jarvis-owned product/backend skeleton:

```text
Browser -> FastAPI -> Jarvis State -> Mock RuntimeAdapter
```

The frozen Stage 1 visual system remains unchanged. Chat now has a small
same-origin serialized API boundary; deterministic visual-review scenes and
Resources/Providers remain synthetic. There is no real Hermes, PDI, Resource
Access, Provider, Tailscale, systemd, or production database integration.

## State ownership

Jarvis persists only Conversation, user-visible Message, Turn, and opaque
MessageResourceRef. Streaming deltas, execution phases, runtime traces, and
tool payloads are not persisted. Only a successful completion transaction
creates the final assistant Message and selected opaque Resource references.
Failed, cancelled, or interrupted Turns have no canonical partial assistant
Message.

Jarvis has independent SQLAlchemy metadata and `jarvis_migrations`, using
`jarvis_alembic_version`. The future production topology is a separate logical
`jarvis` database and role, even if it shares the PostgreSQL server with `pdi`.
Stage 2 creates neither in production.

## Runtime and streaming

The framework-independent RuntimeAdapter contract is async-native and exposes
start, event stream, and idempotent cancellation. Jarvis events carry a Turn ID
and monotonic sequence and expose only product-safe phases and user-visible
assistant deltas. Active execution, provisional text, subscribers, and bounded
replay are process-local because V0.1 is explicitly one worker. An SSE client
disconnect does not cancel a Turn. Startup atomically marks orphaned persisted
`running` Turns as `interrupted` without replay or retry.

The deterministic mock exercises completion, cancellation, controlled failure,
slow streaming, replay, and reconnect against the same contract intended for a
future Hermes adapter. `MockRuntimeAdapter` is selected only at the application
composition or test boundary. Browser requests, query parameters, request
bodies, cookies, headers, and frontend routes cannot select the Runtime
implementation or a mock scenario. Stage 3 replaces the composed mock with
`HermesRuntimeAdapter`; it does not change the browser contract.

`POST /turns/{turn_id}/cancel` has a synchronous-terminal contract. For a
successfully cancelled running Turn, the response observes `cancelled` only
after the Runtime terminal event is consumed, the canonical Turn status is
committed without an Assistant Message, and the terminal event is published to
the active registry. `TurnCoordinator` synchronizes on the exact existing
consumer task for that Turn; cancellation authority must not be implemented by
an arbitrary polling or sleep window. Shielding that consumer from request
cancellation preserves terminal processing even if the HTTP client disconnects.

## Browser and authentication security

All application requests pass through an injected `AuthAdapter` and expose a
JarvisPrincipal to product code. The production-intended Tailscale adapter
requires both a trusted localhost proxy peer and an exact
`Tailscale-User-Login` allowlist match. Tests inject TestAuthAdapter directly;
there is no runtime development bypass, user table, login, password, or JWT.
This freezes production-intended validation logic, not production-validated
authentication. Real Tailscale Serve, proxy-peer and loopback behavior, header
injection, and negative identity cases remain Stage 5 host validation.

State-changing API requests require the exact configured Origin,
`application/json`, and `X-Jarvis-Request: web-v1`. SSE is an authenticated,
read-only GET; cancellation is a separate protected POST. CORS is absent.
Security headers include a same-origin CSP, frame denial, nosniff, no-referrer,
and a bounded Permissions Policy. API and SSE responses are private/no-store.

## Layer enforcement

The obsolete direct-persistence `src/jarvis/bootstrap.py` PoC had no formal
runtime or production dependency and is removed. Automated architecture tests
enforce:

- Jarvis does not import PDI database, repository, or ORM internals;
- PDI does not import Jarvis;
- Jarvis state does not import PDI;
- the runtime contract imports no FastAPI, SQLAlchemy, or Hermes module; and
- frontend source contains no Provider endpoint, PDI UDS path, database URL,
  WebSocket, service worker, or secret boundary.

## Deployment status

FastAPI can serve the Vite `dist` directory same-origin with an API-preserving
SPA fallback. No production Node server is required. Stage 2 does not create a
production database or role, run production migrations, launch Uvicorn, bind a
production port, or modify systemd/Tailscale.

## Frozen deferrals

- Real Hermes Runtime integration is Stage 3.
- Real PDI consumer and Resource Access integration is Stage 4.
- Production database/service creation, Tailscale Serve, and host authentication
  validation are Stage 5.
