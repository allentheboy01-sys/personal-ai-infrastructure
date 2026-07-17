# 08 - Repository

**Status:** Stable for Identity V1

## Purpose

The Repository is the persistence boundary of the PDI World Model.

It provides domain-oriented queries to Identity and executes Decisions while hiding storage-specific details such as SQL, ORM mappings, sessions, transactions, and database engines.

## Responsibilities

A Repository is responsible for:

- querying Assets, Blobs, and AssetSources;
- finding Sources by Provider identity;
- finding Blobs by content hash;
- listing active Sources for one Provider;
- executing Decisions;
- preserving Action order;
- enforcing persistence-level integrity;
- committing a complete Decision atomically;
- rolling back failed persistence operations;
- translating between domain objects and storage representations.

## Read Contract

Identity reads the World Model only through Repository interfaces.

Current query responsibilities include:

```text
find_source(provider, external_id)
list_active_sources(provider)
find_blob_by_hash(content_hash)
find_blob_by_hash_in_asset(asset_id, content_hash)
get_blob(blob_id)
get_asset(asset_id)
```

The exact implementation may evolve, but callers must not depend on internal collections, ORM objects, SQL tables, or session state.

## Execution Contract

The Repository executes a `Decision` transactionally.

```text
Decision
   │
   ▼
Repository.execute()
   │
   ├── preserve Action order
   ├── persist domain changes
   ├── flush dependencies when required
   └── commit or roll back atomically
```

A failure during execution must not leave a partially applied Decision.

## Supported Actions

Identity V1 Repository implementations execute:

```text
CREATE_ASSET
CREATE_BLOB
CREATE_SOURCE
UPDATE_SOURCE
DEACTIVATE_SOURCE
```

The Repository applies the supplied state. It does not reconsider whether the Action was semantically correct.

## Does NOT

A Repository does not:

- connect to Providers;
- parse Provider-specific data;
- coordinate synchronization;
- calculate hashes;
- decide whether content changed;
- decide whether a Source disappeared;
- create business Decisions;
- infer relationships or semantic identity.

## Storage Independence

The domain architecture must not depend on PostgreSQL, SQLAlchemy, or an in-memory implementation.

Current implementations may include:

- `InMemoryRepository` for isolated tests and development;
- `PostgreSQLRepository` for persistent runtime storage.

Equivalent Repository implementations must preserve equivalent domain behavior.

## ORM Boundary

ORM models are persistence representations, not World Model domain objects.

The Repository is responsible for mapping between:

```text
Domain Entity
    ⇄
Persistence Representation
```

ORM-specific concepts must not leak into Identity, Decision, Adapter, or Sync Engine code.

## Invariants

1. Repository queries expose domain meaning, not storage structure.
2. A Decision is executed atomically.
3. Action order is preserved.
4. Foreign-key dependencies are satisfied without splitting one Decision into independent commits.
5. Failed execution is rolled back.
6. Repository does not invent business meaning.
7. Soft deletion preserves Source rows and historical references.
8. Storage implementations remain replaceable.

## Current Implementation

The current persistent implementation uses:

- PostgreSQL;
- SQLAlchemy 2.x Typed ORM;
- explicit transaction control;
- ordered flushes for dependent entities;
- integration tests against a real PostgreSQL database.

These are implementation choices, not permanent architecture requirements.

## Related Documents

- [06 - Identity](06-identity.md)
- [07 - Decision](07-decision.md)
- [09 - World Model](09-world-model.md)
- [11 - Sync Lifecycle](11-sync-lifecycle.md)
