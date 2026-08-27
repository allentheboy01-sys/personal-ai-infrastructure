# PDI Current Public Context

This file records the public implementation boundary. Private host state,
production counts, credentials, incident details, and deployment chronology do
not belong here.

## Product position

PDI is provider-independent Personal Digital Infrastructure. It owns durable
Resource identity, deterministic observations, query/retrieval contracts, and
controlled Resource access independently of any Provider or AI runtime.

The dependency direction is:

```text
Providers -> Adapters -> PDI Core -> Public services / MCP -> Consumers
```

Jarvis is the first substantial reference consumer retained in the monorepo.
It is optional and replaceable. PDI has no dependency on Jarvis or DeepSeek
Harness, and no DeepSeek Harness integration is claimed by the current source.

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

The repository includes deployment assets derived from one validated
self-hosted installation. They remain reference material pending Public
Readiness Phase D parameterization and must not be treated as portable defaults.
See `docs/deployment/README.md`.

## Public-readiness status

Phase A+B establishes the privacy and product boundary:

- real content-derived discovery fingerprints are removed from current HEAD;
- private operations are separated from public documentation;
- contributor guidance is host-neutral;
- PDI is the primary documentation identity; and
- Jarvis is positioned as a reference consumer.

The following work remains deliberately deferred:

- Phase C: full public README and documentation rewrite;
- Phase D: configuration and deployment portability; and
- Phase E: OSS metadata, CI, pinned secret scanning, and public verification.

The README currently names milestone `v0.6` while `pyproject.toml` remains
`0.5.0`. Public version alignment is a Phase C/E decision, not part of this
boundary-only change.
