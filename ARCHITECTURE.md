# PDI Architecture

## Project Position

PDI is Personal Digital Infrastructure: a durable foundation for a person's
digital life that remains useful independently of any one Provider, storage
product, AI model, or interface.

Jarvis is the first AI Interface built on top of PDI. Keeping it outside PDI
Core preserves the distinction between infrastructure and consumer:

```text
Jarvis → PDI
```

The reverse dependency is prohibited. PDI must remain usable when Jarvis is
removed or replaced.

## Overall Architecture

```text
User
  ↓
Consumer / AI Interface
  ↓
PDI Application Service
  ↓
PDI Core and Repository Contracts
  ↓
PostgreSQL World Model

Providers
  ↓
Adapters
  ↓
PDI Write Pipeline
```

The architecture separates changing edges from stable internal contracts.
Providers enter through Adapters. Consumers enter through Application
Services. Neither side defines the World Model or bypasses its boundaries.

PDI contains two distinct data paths:

```text
Write: ProviderFact → SyncEngine → Decision → DecisionRepository

Read:  QueryService → QueryRepository → immutable Read Model
```

The same PostgreSQL Repository may implement both repository contracts, but
the contracts and responsibilities remain separate.

## PDI Core

PDI Core maintains provider-independent identity and lifecycle rules.

The Write Pipeline translates observations into controlled World Model
changes:

```text
Provider
  ↓
Adapter
  ↓
ProviderFact
  ↓
SyncEngine
  ├── Identity / Matcher
  ├── Requirement / Capability
  └── Decision
        ↓
DecisionRepository
```

The Core owns concepts such as Asset, Blob, and AssetSource. Provider-specific
concepts stay behind Adapter boundaries, while AI-specific concepts stay in
consumer packages.

This prevents a richer Provider or a newer AI model from forcing unnecessary
changes into stable personal identity semantics.

## Jarvis

Jarvis is a consumer application in the separate `src/jarvis` package. Its
current execution path is:

```text
ToolCall
  ↓
JarvisApplication
  ↓
ToolRegistry
  ↓
Tool
  ↓
PDI QueryService
```

`JarvisApplication` only resolves and executes Tools. It does not understand
specific Tool arguments, query PDI directly, or access persistence.

Each Tool owns its parameter validation and translates expected business
outcomes into stable `ToolResult` errors. Unexpected failures are contained at
the Application boundary and logged without exposing internal details to the
caller.

New Tools should require only a new Tool implementation, registration in the
Composition Root, and tests. They should not require changes to the execution
core.

## Provider

A Provider is an external system that owns its own representation and
behavior. Nextcloud and Immich are the current real Providers.

An Adapter translates Provider observations into `ProviderFact` and opens
content only when the SyncEngine requests additional evidence. It does not
create World Model entities, make identity decisions, or access a Repository.

Providers remain replaceable because PDI Core consumes the shared Adapter
contract rather than Provider APIs directly.

## Application Service

Application Services are the public use-case boundary for consumers.

The current Read Application Service is `QueryService`, which provides:

- `list_assets()`;
- `get_asset(asset_id)`.

It returns immutable Query Read Models rather than ORM or Domain objects. This
gives consumers a stable contract while allowing persistence and internal
models to evolve independently.

Jarvis Tools depend on this service. They must not import a concrete
Repository, SQLAlchemy, Session, Engine, database model, or Adapter.

## Repository

Repository contracts isolate persistence from business and consumer logic.

The Write side uses a Decision Repository to execute already-decided changes.
The Read side uses `QueryRepository` to produce stable Read Models. These
interfaces remain separate even though `PostgreSQLRepository` implements both.

SQLAlchemy ORM objects and Sessions stay inside the PostgreSQL Repository.
Read Model mapping is completed while a Session is active, and returned values
remain usable after that Session closes.

This design keeps transaction and query mechanics out of the Core,
Application Services, Jarvis, and Tools.

## Future Extension Direction

Future capabilities should extend the established boundaries instead of
bypassing them:

- new Providers enter through new Adapters;
- new consumer operations enter through public Application Services;
- new Jarvis capabilities enter through registered Tools;
- external transports call the Jarvis Application boundary;
- persistence changes remain behind Repository contracts.

HTTP transport, content access, search, relationships, tasks, and LLM
integration are not part of the current architecture until their respective
designs are discussed and frozen.

The governing rule remains:

> Architecture before implementation. A new abstraction must reduce total
> complexity.
