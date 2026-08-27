# PDI — Personal Digital Infrastructure

PDI is a provider-independent infrastructure layer for a person's digital
life. It turns records held by changing services into durable, queryable
Resources and evidence that remain under the individual's control.

PDI is the product. Jarvis is an optional reference consumer that demonstrates
how a replaceable AI runtime can use PDI through stable boundaries; it is not
PDI Core, a required UI, or the only supported consumer.

## Why PDI

AI products, models, and storage providers change faster than a person's
digital life. PDI keeps identity, observations, retrieval, and controlled
content access outside any one AI product so future interfaces can use the
same durable World Model without owning it.

## Architecture

```text
Providers
   |
Adapters
   |
PDI Core / Personal Digital World
   |
Query / Retrieval / Resource Access / MCP
   |
Optional consumers and AI runtimes
```

The current implementation has four explicit paths:

- **Write:** Nextcloud, Immich, and Gmail Adapters produce ProviderFacts for the
  incremental, idempotent Sync Engine.
- **Observation:** deterministic enrichment publishes typed, evidenced
  statements without changing Resource identity.
- **Read and retrieval:** structured queries, aggregation, Provider-semantic
  retrieval, and rich statement-aware retrieval return immutable models.
- **Resource access:** bounded streaming representations expose eligible
  Provider content without leaking credentials or persistence internals.

Consumers use application services, MCP, or Resource Access. They do not own
PDI persistence and must not access Provider credentials or PDI ORM/database
internals directly.

## Current status

The repository currently identifies its operational-hardening milestone as
`v0.6`. PDI includes Provider synchronization, PostgreSQL/Alembic persistence,
deterministic observations, query and retrieval services, bounded Resource
Access, and a read-only MCP surface. Nextcloud, Immich, and a bounded Gmail
Provider are implemented at different maturity levels.

Jarvis runtime and Web code remain in this monorepo temporarily as a reference
consumer. Their implementation and historical validation records do not define
PDI's public contract. A later repository-boundary review may split Jarvis
without changing PDI Core.

The README milestone and Python package version are not yet aligned; version
policy and release metadata are explicitly deferred to Public Readiness Phase
C/E.

## Development

The current contributor baseline uses Python 3.13 and an isolated environment:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -e . pytest
.venv/bin/python -m pytest -q
```

This is not yet the final public Quick Start. See the
[local development guide](docs/development/local-development.md) for test and
production-isolation rules.

## Documentation

Start with the [documentation index](docs/README.md), then read the
[architecture](ARCHITECTURE.md). Security reports and private-data handling are
covered by [SECURITY.md](SECURITY.md).

## License

PDI is available under the terms in [LICENSE](LICENSE).
