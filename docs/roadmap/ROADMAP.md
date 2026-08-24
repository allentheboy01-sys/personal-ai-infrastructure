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
  a historical PipelineRun ledger, ten tracked formal pipelines, derived
  freshness signals, and the eighth read-only MCP Tool. Server-first Codex
  migration is complete. Minimal Person Identity V0.1 is also production active
  for the standard Immich enumerable People inventory, without names or face
  data. Resource-Person Relation V0.1 is production active through one dedicated
  provider-owned `depicts` table, with 10,460 active Immich-derived mappings,
  no generic graph, MCP exposure, or scheduling. Typed Resource V0.1 is
  production active on the existing `assets.id` identity with bounded
  `file|message` types. Gmail Provider V0.1 is functionally frozen for one
  account with 283 production Message Resources, RAW RFC 2822 Blobs, four
  deterministic predicates, and two manually invoked tracked pipelines. It
  adds no scheduler, timer, systemd service, or MCP Tool; unattended operation
  remains blocked on the OAuth lifecycle. Jarvis Web UI V0.1 Stage 1 is frozen
  as a frontend-only static React product shell with synthetic data and no
  production service. Stage 2 state/FastAPI contracts and the Stage 3 isolated
  HermesRuntimeAdapter are frozen after human architecture/runtime review.
  Stage 4 deterministic read-only PDI views, Provider status projection, and
  bounded Resource Access proxy are frozen after human integration review and
  real-browser validation. Stage 5B Gate E.6 freezes the real-host-validated
  Jarvis Exec Sandbox V0.1: five bounded execution/workspace MCP tools run in a
  per-connection DynamicUser sandbox with no network, product secrets, private
  home, Docker, persistent workspace, or authoritative state. Gate E.8.4 freezes
  cancellation as synchronous-terminal using the exact Turn consumer task,
  explicitly rejecting arbitrary polling as synchronization authority. The
  `e8125009` artifact is superseded; a new immutable release and versioned venv
  must be built before the separately reviewed production activation retry.
  Person Label Retrieval V0.1 has a source-frozen contract: it
  preserves Provider-declared current labels on PersonSource and adds an exact,
  relation-backed primary to the existing rich retrieval Tool without adding a
  Tool, canonical Person name, or language inference. Production activation is
  a separately validated additive migration plus the existing explicit Person
  scan; the migration itself performs no label backfill or identity rewrite.
  Jarvis Person Query Interpretation V0.1 is an implementation candidate that
  adds bounded current Person-label discovery to the existing aggregate Tool
  and concise Hermes grounding/stop guidance, without a new Tool, schema,
  persistent alias store, family ontology, Runtime protocol, or frontend change.

## Future

- Consumer-facing relationship retrieval and broader cross-resource reasoning,
  only after a separate architecture review.
- User-controlled memory derived from PDI rather than owned by an AI runtime.
- Explicit permission and write/action boundaries before any write-capable
  consumer Tool is introduced.
- Jarvis Web authentication and production deployment only through their
  separately reviewed Stage 5 boundaries. General Internet/Web capability is
  separate from Exec and must not be added by enabling arbitrary Exec network.
- **v1.0 — Stable Personal Digital Infrastructure:** stabilize proven provider,
  observation, retrieval, access, and consumer contracts for long-term use.

Future milestones are directional and subject to architecture review.
