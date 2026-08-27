# PDI Architecture

## Position

PDI is Personal Digital Infrastructure: a durable foundation for a person's
digital life, independent of any one Provider, storage product, model, or AI
interface. Jarvis is the first validated consumer; Codex is a development
tool. Neither is part of PDI Core.

The dependency rule is one-way:

```text
Consumer / AI runtime -> PDI
```

PDI must remain useful if every current consumer and model is replaced.

## System map

```text
Nextcloud / Immich / Gmail
        |
     Adapters
        |
  Provider Facts
        |
    Write Pipeline --------------------+
                                      |
Provider metadata/content             v
        |                         PostgreSQL World Model
 Observation Extraction               ^        ^
        |                              |        |
 Typed evidenced Statements ----------+   Query / Retrieval
                                               |
                                   PDI MCP / Resource Access
                                               |
                                     Consumer / AI runtime
```

The implementation separates four paths so a richer consumer cannot rewrite
identity rules and a richer Provider cannot leak into public contracts.

## Write path

```text
Provider -> Adapter -> ProviderFact -> SyncEngine
                                      |-> Identity / Matcher
                                      |-> Requirement
                                      `-> Decision -> DecisionRepository
```

Adapters translate Provider observations and open content only when the Sync
Engine requests evidence. They do not create World Model entities, decide
identity, or access repositories.

The Core owns Asset, Blob, and AssetSource identity and lifecycle. Synchronism
is incremental and idempotent; full scans can reconcile missing sources by
soft deactivation without destroying durable identity.

Every independently addressable digital object should preferentially have a
canonical PDI Resource identity. This does not turn every fact or operational
state into a Resource: Observation, Relation, Person, Provider source, and
PipelineRun remain separate concepts. The physical persistence table remains
named `assets`; conceptual and public contracts use Resource.

## Observation path

```text
Resource + Source metadata/content
        |
 deterministic Extractor
        |
 ObservationBatch
        |
 ObservationService -> ObservationRepository -> PostgreSQL
```

Observations add typed, evidenced statements to a Resource without changing
its identity. Predicate definitions fix value type and cardinality. Each batch
records generator identity, covered predicates, input fingerprint, evidence,
and statement lifecycle so reruns are deterministic and supersession is
explicit.

Current extractors cover Immich provider metadata, OCR and geo labels, file
modification time, Nextcloud text and PDF/DOCX/ODT content, plus deterministic
Gmail Subject/From/To/internal-date facts. Extractors do not make open-ended AI
interpretations.

## Read and retrieval path

```text
Consumer -> Application Service -> Repository contract -> PostgreSQL
                    |
             immutable Read Model
```

The read surface consists of:

- `QueryService` for recent/search/detail, aggregation, filters, and cursor
  pagination;
- `RetrievalService` for Provider-semantic retrieval;
- `RichRetrievalService` for primary text retrieval combined with typed
  Observation filters; and
- `DataStatusService` for bounded pipeline execution and objective freshness
  signals from the PipelineRun ledger.

Resource references use `pdi:resource:<uuid>`. Time semantics distinguish PDI
first-observed time, captured time, and file-modified time. Repository mapping
finishes while a SQLAlchemy Session is active; ORM objects, sessions, engines,
and concrete repositories never cross the service boundary.

## Resource access path

Resource access is separate from query and retrieval:

```text
Resource reference + approved access kind
        |
ResourceAccessService -> eligible Provider source -> controlled byte stream
```

It returns controlled representations rather than filesystem paths or Provider
credentials. Image and video thumbnails remain bounded image representations.
Video playback is a distinct streaming contract that preserves validated
single-range HTTP semantics without buffering the media body. Eligibility,
upstream validation, concurrency, and stream cleanup are enforced at the
service boundary. The deployed process uses its own launcher and
Unix-domain-socket/HTTP boundary.

## MCP boundary

PDI MCP is the read-only consumer boundary. It composes the public services and
serializes stable results. It currently exposes eight Tools for data status,
recent, search, aggregation, Provider-semantic retrieval, rich retrieval,
Resource detail, and Resource observations.

MCP Tool handlers must not import ORM types, open database sessions directly,
or receive Provider credentials. A runtime may expose a deliberately smaller
subset. The current Jarvis Web UI V0.1 runtime-integration baseline exposes
seven read-only Tools: recent, search, Resource detail, aggregation,
Observations, Provider-semantic retrieval, and rich retrieval.

## Consumer and deployment boundary

PDI Core does not require a particular hostname, filesystem layout, service
manager, private-network product, model provider, or AI runtime. Deployments
must keep development/test data separate from production data, protect Provider
credentials, and expose only the public PDI service boundaries they need.

The repository includes deployment assets derived from one validated
self-hosted installation. Until Public Readiness Phase D parameterizes them,
they are reference material rather than portable defaults.

Jarvis is a separate consumer boundary. Its application state, migrations,
runtime adapters, Web access, and execution sandbox are not PDI Core. It must
consume PDI through public application services, MCP, or Resource Access and
must not reach into PDI persistence. Hermes is one replaceable Jarvis runtime
implementation; neither Jarvis nor Hermes is required to install or use PDI.

Potential future consumers, including other MCP-capable agents, must follow the
same one-way dependency rule. PDI does not currently depend on or claim an
integration with DeepSeek Harness.

Formal batch execution is scheduler-independent: `pdi.operational` is the sole
owner of `/run/lock/pdi-sync.lock`, records independently committed PipelineRun
start and terminal states, and invokes the existing Provider sync or enrichment
CLI. Bare CLIs remain untracked development/debug entrypoints.

## Invariants

- PDI Core depends on no AI runtime or model.
- Provider-specific behavior remains behind Adapters or access providers.
- Identity changes only through the Write Pipeline.
- Observation enrichment never mutates Resource identity.
- Public services return stable immutable models or bounded streams.
- MCP is read-only until a separately reviewed write/action boundary exists.
- Production secrets never enter Git, prompts, logs, or test processes.
- Production updates are clean and fast-forward-only.

## Future extension

New Providers enter through Adapters. New deterministic knowledge enters
through registered predicates and extractors. New query behavior enters public
Application Services and repository contracts. New AI capabilities enter as
consumer Tools over those services.

Relationships, long-term user-controlled memory, write actions, and task
systems require their own trust and architecture freeze before implementation.
A new abstraction must reduce total complexity.

The former `src/jarvis/bootstrap.py` legacy proof of concept directly composed
PDI persistence. No formal runtime or production path depended on it, so Stage
2 removed it from the active package. New Jarvis consumers must use public
Application Services or MCP and must not import PDI repository, ORM, session,
engine, or database modules.
