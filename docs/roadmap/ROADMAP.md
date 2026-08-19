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

- **v0.6 — Operational hardening:** Immich Geo Enrichment V0.1 production
  enrichment, idempotency, service installation, and daily 05:30 timer are
  complete and frozen. Data Status & Freshness V0.1 is production active with
  a historical PipelineRun ledger, eight tracked formal pipelines, derived
  freshness signals, and the eighth read-only MCP Tool. Server-first Codex
  migration is complete. Minimal Person Identity V0.1 is also production active
  for the standard Immich enumerable People inventory, without names or face
  data. Resource-Person Relation V0.1 is production active through one dedicated
  provider-owned `depicts` table, with 10,460 active Immich-derived mappings,
  no generic graph, MCP exposure, or scheduling. Typed Resource V0.1 is
  production active on the existing `assets.id` identity with bounded
  `file|message` types; all 15,325 pre-existing Resources remain `file`, Blob
  remains mandatory, and Gmail is not implemented. The next formal architecture
  stage requires human discussion and is not selected by this roadmap update.

## Future

- Consumer-facing relationship retrieval and broader cross-resource reasoning,
  only after a separate architecture review.
- User-controlled memory derived from PDI rather than owned by an AI runtime.
- Explicit permission and write/action boundaries before any write-capable
  consumer Tool is introduced.
- A transport/UI only after its trust, authentication, and deployment model is
  frozen.
- **v1.0 — Stable Personal Digital Infrastructure:** stabilize proven provider,
  observation, retrieval, access, and consumer contracts for long-term use.

Future milestones are directional and subject to architecture review.
