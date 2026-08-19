# PDI — Personal Digital Infrastructure

PDI is a provider-independent infrastructure layer for a person's digital
life. It turns records held by changing services into durable, queryable
Resources and evidence that remain under the individual's control.

Jarvis is the first validated AI interface on top of PDI. It is a replaceable
consumer, not the project itself.

## Why PDI

AI products, models, and storage providers change faster than a person's
digital life. PDI keeps identity, observations, retrieval, and controlled
content access outside any one AI product so future interfaces can use the
same durable World Model without owning it.

## Architecture

```text
Providers                    Consumers / AI runtimes
   |                                  |
Adapters                              MCP
   |                                  |
Write Pipeline -> PostgreSQL <- Query / Retrieval Services
                         |
                  Resource Access
```

The current implementation has four explicit paths:

- **Write:** Nextcloud, Immich, and Gmail Adapters produce provider facts for the
  incremental, idempotent Sync Engine.
- **Observation:** deterministic enrichment publishes typed, evidenced
  statements without changing Resource identity.
- **Read and retrieval:** structured queries, aggregation, provider-semantic
  retrieval, and rich statement-aware retrieval return immutable models.
- **Resource access:** bounded streaming representations expose eligible
  provider content without leaking credentials or persistence internals.

## Current status

**Current release:** `v0.6` — Operational Hardening

The release includes:

- Nextcloud and Immich synchronization with PostgreSQL and Alembic migrations;
- Resource projection, stable `pdi:resource:<uuid>` references, pagination,
  aggregation, and temporal filtering;
- typed Observation statements and deterministic enrichment for provider
  metadata, Immich OCR and geo labels, file modification time, Nextcloud text,
  PDF, DOCX, and ODT content;
- provider-semantic and rich retrieval, including captured/file-modified time
  predicates;
- bounded streamed Resource representations;
- eight read-only PDI MCP Tools, including bounded data-pipeline status;
- a validated on-demand Jarvis/Hermes reference runtime on `pdi-server`;
- systemd synchronization, enrichment, and resource-access deployment assets;
- a formal PipelineRun ledger with one scheduler-independent lock owner;
- stable Person identity plus one dedicated Immich-derived Resource-depicts-
  Person relation table, without face/vector persistence or a generic graph;
- typed Resource identity on the existing `assets.id`, with explicit `file`
  and `message` types while Blob remains mandatory;
- frozen single-account Gmail ingestion for 283 production Message Resources,
  exact RAW RFC 2822 Blobs, and four deterministic metadata predicates; and
- the frozen Jarvis Web UI V0.1 Stage 1 static React frontend, with synthetic
  data only, responsive Chat/Resources/Providers surfaces, and the Beacon / Guide
  product mark;
- the implemented, not-yet-deployed Stage 2 Jarvis State/FastAPI skeleton with
  a composition-only MockRuntimeAdapter and persistent same-origin Chat
  boundary, frozen after human architecture review;
- the frozen Stage 3 one-process-per-Turn
  HermesRuntimeAdapter with a private bounded JSONL bridge, canonical Jarvis
  history input, exact process-group cancellation/cleanup, live phase events,
  and safe final-only response delivery; and
- a server-first Codex CLI development workflow with production isolation.

Current host-safe/default validation: `512 passed, 98 skipped`. The Stage 3
Jarvis migration validation is `1 passed` against a disposable isolated
PostgreSQL database. The prior full PDI isolated validation is `99 passed, 2
skipped`; the two skips require live Immich credentials. Integration,
live-Provider, and database tests are
explicitly gated and are never run against production data. Gmail V0.1 is
functionally frozen for bounded manual execution; unattended operation remains
blocked on the OAuth application lifecycle.
The v0.5.0 release-preparation baseline was `412 passed, 66 skipped`.

## Development

Use Python 3.13 and an isolated environment:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -e . pytest
.venv/bin/python -m pytest -q
```

Repository rules for Codex and human contributors live in
[`AGENTS.md`](AGENTS.md). The host workflow, chat continuity, memory model, and
authentication boundary are documented in
[`docs/development/codex-cli-on-pdi-server.md`](docs/development/codex-cli-on-pdi-server.md).

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Current Context](docs/context/CURRENT_CONTEXT.md)
- [Roadmap](docs/roadmap/ROADMAP.md)
- [v0.5.0 release notes](docs/releases/v0.5.md)
- [v0.6 operational hardening notes](docs/releases/v0.6.md)
- [Gmail Provider V0.1 design](docs/design/pdi-gmail-provider-v0.1.md)
- [Production server runtime](docs/deployment/server-runtime-v0.1.md)
- [Jarvis reference runtime](docs/deployment/jarvis-runtime-server-v0.1.md)
- [Jarvis Web UI V0.1 Stage 1 freeze](docs/design/jarvis-web-ui-v0.1-stage1-freeze.md)
- [Jarvis Web UI V0.1 Stage 2 skeleton](docs/design/jarvis-web-ui-v0.1-stage2.md)

## License

PDI is available under the terms in [LICENSE](LICENSE).
