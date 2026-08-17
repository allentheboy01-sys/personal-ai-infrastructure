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

- **Write:** Nextcloud and Immich Adapters produce provider facts for the
  incremental, idempotent Sync Engine.
- **Observation:** deterministic enrichment publishes typed, evidenced
  statements without changing Resource identity.
- **Read and retrieval:** structured queries, aggregation, provider-semantic
  retrieval, and rich statement-aware retrieval return immutable models.
- **Resource access:** bounded streaming representations expose eligible
  provider content without leaking credentials or persistence internals.

## Current status

**Current release:** `v0.5.0` — Personal Retrieval Runtime

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
- seven read-only PDI MCP Tools;
- a validated on-demand Jarvis/Hermes reference runtime on `pdi-server`;
- systemd synchronization, enrichment, and resource-access deployment assets;
  and
- a server-first Codex CLI development workflow with production isolation.

Current `main` validation: `414 passed, 66 skipped`. Skipped tests are the
explicit external/database integration gates and are not run against production
data. The v0.5.0 release-preparation baseline was `412 passed, 66 skipped`.

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
- [Production server runtime](docs/deployment/server-runtime-v0.1.md)
- [Jarvis reference runtime](docs/deployment/jarvis-runtime-server-v0.1.md)

## License

PDI is available under the terms in [LICENSE](LICENSE).
