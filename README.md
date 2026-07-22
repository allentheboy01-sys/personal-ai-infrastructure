# PDI

## Personal Digital Infrastructure

PDI is a stable, provider-independent infrastructure layer for a person's
digital life. It turns data held by changing services into durable,
queryable digital assets that remain under the individual's control.

Jarvis is the first AI Interface built on top of PDI. It is a consumer of
PDI, not the project itself.

## Why PDI

AI products will change. LLMs will change. The services that hold personal
photos, documents, and other digital records will change too.

A person's data has a much longer lifecycle than any one model, application,
or Provider. If every AI system owns its own isolated memory, changing tools
means losing continuity.

PDI provides the stable foundation beneath those changing systems. It keeps
personal digital identity and access independent from any particular AI or
Provider, so future applications can understand the same durable digital
life without owning it.

## Core Architecture

```text
User
  ↓
Jarvis
  ↓
PDI Core
  ↓
Providers
  ↓
Storage
```

- **User** — owns the digital life represented by the system.
- **Jarvis** — the first AI-facing consumer of PDI's public services.
- **PDI Core** — maintains stable identity, synchronization, and query
  boundaries independently of any one Provider or AI.
- **Providers** — existing systems such as Nextcloud and Immich, connected
  through replaceable Adapters.
- **Storage** — persists PDI's provider-independent World Model in
  PostgreSQL.

Provider data enters PDI through a shared Write Pipeline. Consumers read the
result through a separate Read Pipeline. Jarvis reaches that Read Pipeline
through registered Tools rather than accessing persistence directly.

## Current Status

**Current version:** `v0.4.0`

Completed:

- Provider Adapter boundary with real Nextcloud and Immich integrations.
- Unified, incremental, and idempotent Write Pipeline.
- Stable Read Pipeline returning immutable query models.
- Jarvis Tool Execution MVP with `list_assets` and `get_asset`.
- PostgreSQL persistence and Alembic-managed schema.
- Real PostgreSQL integration coverage.

Next:

- Jarvis HTTP API discussion and architecture definition for `v0.5`.

## Design Principles

- PDI is the infrastructure.
- Jarvis is one consumer.
- Providers are replaceable.
- AI models and interfaces are replaceable.
- Personal data and identity must outlive individual technologies.
- PDI does not depend on Jarvis.
- Consumers use public Application Services, not persistence internals.
- Architecture comes before implementation.
- New abstractions must reduce total complexity.

## Documentation

- [Roadmap](docs/roadmap/ROADMAP.md) — where the project is going.
- [Architecture](ARCHITECTURE.md) — how the system is divided and why.
- [Current Context](docs/context/CURRENT_CONTEXT.md) — the current frozen
  implementation state.

## License

PDI is available under the terms in [LICENSE](LICENSE).
