# PDI Current Public Context

This is a contributor-facing implementation snapshot, not the public product
introduction or an installation guide. Start with `README.md`. Private host
state, production counts, credentials, incident details, and deployment
chronology do not belong here.

## Product position

PDI is provider-independent Personal Digital Infrastructure. It owns durable
Resource identity, deterministic observations, query/retrieval contracts, and
controlled Resource access independently of any Provider or AI runtime.

The dependency direction is:

```text
Providers -> Adapters -> PDI Core -> Public services / MCP -> Consumers
```

Jarvis is the first substantial reference consumer retained in the monorepo.
It is optional and replaceable. PDI has no dependency on Jarvis or another
consumer runtime, and no additional runtime integration is currently claimed.

## Implemented PDI capabilities

- Provider Adapters for Nextcloud, Immich, and bounded Gmail ingestion.
- Incremental, idempotent synchronization into PostgreSQL through the PDI
  identity, requirement, decision, and repository boundaries.
- Streaming Nextcloud traversal with non-authoritative handling for Resources
  that disappear between observation and content read.
- Typed deterministic Observation extraction and evidenced statements.
- Query, aggregation, Provider-semantic retrieval, and rich retrieval services.
- Stable `pdi:resource:<uuid>` references and bounded Resource Access.
- A read-only MCP consumer boundary and formal PipelineRun status projection.
- Typed Resources, minimal Person identity, and a dedicated Provider-derived
  Resource/Person relation without introducing a generic graph.

## Consumer boundary

Consumers use public application services, MCP, or bounded Resource Access.
They do not import PDI repositories, ORM models, sessions, engines, database
modules, or Provider credentials.

Jarvis validates this replaceable-consumer model. Its runtime, Web application,
database, deployment assets, and public-Web capability are not part of PDI Core.
Historical Jarvis Stage/Gate records are reference material rather than the
primary PDI roadmap.

## Development and deployment

Development uses Python 3.13, a repository-local virtual environment, and the
host-safe test suite. Database integration tests require an explicit isolated
test database and must never use production data.

The repository includes a portable manual self-host path with independent
Provider configuration, stable `pdi sync` / `pdi mcp` commands, a loopback-only
PostgreSQL 16 reference, and generic systemd examples. These are reference
deployment choices rather than PDI Core requirements. See
`docs/getting-started/self-host.md` and `docs/deployment/README.md`.

## Public-readiness status

Phases A-E establish the privacy, product, documentation, portability, and
release-verification boundary:

- real content-derived discovery fingerprints are removed from current HEAD;
- private operations are separated from public documentation;
- contributor guidance is host-neutral;
- PDI is the primary documentation identity; and
- Jarvis is positioned as a reference consumer;
- the README explains the product category, current Provider support, consumer
  interfaces, and pre-1.0 maturity; and
- the documentation index separates product guidance from contributor context
  and historical records; and
- a clean checkout can configure one Provider, apply migrations, run a manual
  sync, and expose the read-only stdio MCP boundary without Jarvis; and
- Python 3.13 CI, isolated PostgreSQL 16 validation, artifact checks,
  dependency constraints, and current/history secret scanning enforce the
  public boundary.

The following release actions remain deliberately deferred:

- human review of the exact public-readiness candidate commit;
- creation of Git tag `v0.6.0` and an optional GitHub Release; and
- any repository rename or package publication.

The latest Git tag remains `v0.5.0`. `pyproject.toml` and the public release
candidate note now agree on `0.6.0`, but the candidate is not released until a
separate Release Gate creates tag `v0.6.0` on the reviewed commit.
