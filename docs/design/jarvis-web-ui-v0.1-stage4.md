# Jarvis Web UI V0.1 — Stage 4 Real PDI Views

## Status

FROZEN — human PDI integration and real-browser validation passed

2026-08-20

## Boundary

Stage 4 adds a Jarvis-owned deterministic read boundary:

```text
FastAPI
  -> PDIClient product contract
  -> one persistent, serialized MCP stdio session
  -> existing protected PDI launcher
  -> eight public read-only PDI tools

Browser representation request
  -> allowlisted Jarvis image proxy
  -> configured Resource Access UDS
```

Jarvis imports no PDI database, repository, ORM, composition, Provider, or
credential module. The MCP launcher and UDS path are deployment composition;
they do not occur in browser schemas or product models. The Jarvis parent does
not receive PDI database credentials.

## ResourceView

`ResourceSummary` and `ResourceDetail` are allowlisted, derived, non-persistent
product views. They expose opaque `resource_ref`, `file|message`, display text,
PDI first-observed time, content-derived `image|document|message|generic`
presentation, bounded Provider provenance, and truthful capabilities. Source
locations, external IDs, checksums, raw observations, generator data, pipeline
data, database IDs, and raw MCP payloads are discarded.

Only an active Immich image advertises thumbnail/preview. Nextcloud document
representation is unavailable under the current Resource Access contract.
Gmail is metadata-only; message body access is not implemented. Conversation
hydration deduplicates and limits references to eight per Message and performs
bounded server-side detail calls; it creates no cache table or PDI batch API.

## ProviderView and DataStatus

The non-secret catalog contains exactly Gmail, Immich, and Nextcloud product
metadata and their registered dependency mapping. One provider aggregation and
one generic DataStatus snapshot produce all three views. Provider counts are
active-source support counts, so their sum need not equal the global unique
Resource count. Pipeline keys, run IDs, raw errors, endpoints, account
identities, and credentials are never serialized.

Gmail is described as manually managed and read-only. `ready` means the latest
represented successful provider sync has been processed by its registered
dependencies; it does not mean live, continuously synchronized, or real-time.

## Lifecycle and failure behavior

One FastAPI worker owns one persistent MCP stdio child. Calls are serialized
until transport concurrency is independently proven. Startup validates the
exact eight-tool generic contract. Child failure fails safely; a request gets
at most one controlled reconnect attempt. Shutdown delegates bounded
process-tree cleanup to the MCP stdio transport. There is no pool, supervisor,
Redis, queue, WebSocket, or per-request child.

Resource Access accepts only a syntactically valid opaque Resource ref and the
`thumbnail|preview` kinds, requires an image response, and caps streams at 2
MiB or 16 MiB. Disconnect closes the upstream context. All API and image
responses remain `private, no-store`; live pages show an unavailable state and
never silently substitute review fixtures.

## Agent-linked resources

Structured extraction remains deferred. The Stage 3 Hermes tool completion
callback is not a frozen PDI-result-only schema boundary: inspecting its
general tool result would require parsing a runtime-specific raw payload.
Stage 4 therefore does not scan arbitrary JSON, prose, Markdown, URLs, or IDs.
Existing `MessageResourceRef` completion semantics remain ready for a future
proven opaque-ref-only signal without browser contract changes.

## Validation freeze

The production-equivalent persistent stdio MCP path, real read-only Resource
and Provider projections, and the bounded Resource Access image path passed
host-native validation. The complete Playwright suite passed in an ephemeral
browser runtime with no production or permanent host dependency change. A
bounded browser smoke then rendered live Resources, a real safe Resource
Detail, an eligible Immich thumbnail through the Jarvis proxy, and exactly the
Gmail, Immich, and Nextcloud Provider summaries. It recorded no screenshots or
private field values.

The synchronous in-process `mcp.Client(server)` path can stall only inside the
Codex command sandbox at the MCP/AnyIO worker-thread boundary. The same MCP
contract tests pass host-native, and the production-equivalent stdio path is
green. This is classified as a test-harness limitation, not a product or
transport blocker; production code contains no workaround for it.

## Deferred production work

No production Jarvis database/role/service, migration, systemd unit, Tailscale
Serve configuration, listener, Provider write, PDI write, or sync is created.
Deployment configuration and real Tailscale authentication remain Stage 5.
