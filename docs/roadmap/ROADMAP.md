# PDI Roadmap

The roadmap records delivery order. Architecture and current implementation
details live in their dedicated documents.

## Completed

- **v0.1 — Write Pipeline MVP:** provider-independent identity decisions and
  persistence.
- **v0.2 — Multi-provider Sync MVP:** incremental, idempotent Nextcloud and
  Immich synchronization.
- **v0.3 — Read Pipeline MVP:** stable query services and immutable Asset Read
  Models.
- **v0.4 — Jarvis Tool Execution MVP:** first consumer execution boundary.
- **v0.5 — Personal Retrieval Runtime:** deployed Resource projection,
  Observation enrichment, structured/provider/rich retrieval, bounded streamed
  representations, read-only MCP, and the validated reference AI runtime.

## Current

- **v0.6 — Operational retrieval hardening:** validate the v0.5 contracts at
  production scale, complete geo enrichment scheduling and retrieval UX, and
  improve release/development automation without weakening production
  isolation.

## Future

- Relationship and cross-resource reasoning over evidenced observations.
- User-controlled memory derived from PDI rather than owned by an AI runtime.
- Explicit permission and write/action boundaries before any write-capable
  consumer Tool is introduced.
- A transport/UI only after its trust, authentication, and deployment model is
  frozen.
- **v1.0 — Stable Personal Digital Infrastructure:** stabilize proven provider,
  observation, retrieval, access, and consumer contracts for long-term use.

Future milestones are directional and subject to architecture review.
