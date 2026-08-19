# Jarvis Web UI V0.1 — Stage 3 HermesRuntimeAdapter

## Status

FROZEN

2026-08-19

## Boundary

Stage 3 adds one replaceable `HermesRuntimeAdapter` behind the frozen
Jarvis-owned Runtime contract:

```text
FastAPI / TurnCoordinator
  -> HermesRuntimeAdapter
  -> one isolated bridge process per Turn
  -> Hermes AIAgent
  -> Hermes tools and the existing PDI MCP child
```

The browser, Conversation/Message/Turn/MessageResourceRef state, API, SSE,
reconnect, cancellation, and successful-completion transaction remain the
Stage 2 contracts. Runtime selection and the bridge command remain application
composition concerns and are never request fields.

## Canonical state and session boundary

Jarvis builds each request from ordered canonical user-visible Messages and a
current user Message that appears exactly once. It supplies no prior Hermes
session ID, history file, state database, reasoning, or tool trace. The bridge
constructs a fresh AIAgent for each Turn with session persistence, memory,
trajectories, and checkpoints disabled. Any private artifacts Hermes still
needs internally are non-authoritative and may be ignored or removed between
Turns. Page reload, retry, and later Turn continuity depend only on Jarvis DB.

## Private bridge protocol

The adapter sends one bounded versioned JSON request over stdin and accepts
bounded JSONL records over stdout: `ready`, product phase, visible text delta,
completion, cancellation, or sanitized failure. The bridge is run as a source
file by the Hermes Python environment, imports no Jarvis/PDI package, and needs
no installation of the Web application into that environment.

Hermes stdout is redirected away from protocol stdout. stderr is continuously
drained but retained only in a bounded private buffer and is never forwarded
to SSE. Reasoning callbacks emit at most the `thinking` phase; their content is
never serialized. Hermes token callbacks may include assistant text from an
intermediate tool-loop iteration, so the bridge deliberately does not publish
them. It emits the returned final response as bounded deltas after filtering
split or complete `<think>` blocks. Therefore SSE event streaming, live phase
streaming, and safe final-response delivery pass, while true final-answer token
streaming is explicitly deferred. A future Hermes capability may enable it
without changing the Jarvis browser or Runtime contracts. Tool callbacks map
names privately to the frozen phases `searching`, `reviewing`, `computing`, or
safe generic `thinking`; names,
arguments, results, Provider payloads, and raw MCP JSON never cross the bridge.

## Process and cancellation semantics

Every bridge starts a new process session. Cancellation sends SIGINT to the
exact bridge process so its signal handler calls `AIAgent.interrupt()`, waits a
bounded grace period, then terminates and, only if necessary, kills that exact
Turn process group. Completion, failure, timeout, malformed protocol, and
cancellation all perform the same final process-group cleanup so bridge-owned
MCP/tool children cannot remain. There is no broad process matching, daemon,
pool, Redis, queue, WebSocket, persistent runtime event table, or execution
recovery after backend restart.

## Configuration and secrets

`HermesBridgeConfig` receives the complete bridge command, working directory,
sanitized environment, timeout, grace periods, and input/output limits at the
composition boundary. It contains no hard-coded host path. The adapter does
not inherit the Web process environment by default. A protected Stage 5
launcher is responsible for loading only the inference secret and supplying
the formal profile environment; the key is never part of bridge JSON, Jarvis
state, browser data, or Git. Existing PDI MCP launchers retain their independent
credential authority.

## Compatibility and profile contract

The explicit host diagnostic executes `hermes_bridge.py --check-profile` with
the Hermes Python environment. It verifies AIAgent, `run_conversation`,
`interrupt`, required callbacks, readable profile configuration, and the exact
seven-tool PDI include list:

- `pdi_list_recent_resources`
- `pdi_search_resources`
- `pdi_get_resource`
- `pdi_aggregate_resources`
- `pdi_get_resource_observations`
- `pdi_retrieve_resources`
- `pdi_rich_retrieve_resources`

Hermes upgrades must rerun this explicit compatibility gate. It is not an
offline unit-test dependency.

## Startup latency decision

The bounded real-host validation measured approximately 2.1 seconds from spawn
to first Runtime event, 6.6–8.0 seconds to first confirmed visible final-answer
delivery, and 7.9–9.4 seconds to completion. This is accepted for single-user
V0.1. Per-Turn subprocess isolation remains frozen; no daemon, process pool,
long-lived Hermes session, queue, or execution recovery is introduced.

## Resource references and deferred scope

Stage 3 emits no real MessageResourceRef because the inspected Hermes callback
surface does not provide a proven stable opaque-resource-ref-only result
contract without raw tool payload parsing. Resource reference projection and
the deterministic PDI client remain Stage 4.

This stage creates no production Jarvis database or role, deploys no Web
service, changes no formal Hermes profile/launcher, and modifies no systemd or
Tailscale configuration. Production deployment and host authentication remain
Stage 5.
