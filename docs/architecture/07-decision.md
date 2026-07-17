# 07 - Decision

**Status:** Stable for Identity V1

## Purpose

A `Decision` is the declarative output of Identity.

It describes what should happen to the World Model or what additional evidence is required before a safe decision can be made.

A Decision never performs those changes itself.

## Structure

A Decision contains:

```text
Decision
├── actions[]
└── requirements[]
```

- `actions[]` describes executable World Model changes.
- `requirements[]` describes missing information required by Identity.

## Requirements

A Requirement is a request for evidence, not an instruction to mutate the World Model.

Current requirement:

```text
CONTENT_HASH
```

When a Requirement is present, the Sync Engine attempts to satisfy it, enriches the fact, and invokes Identity again.

A Decision with unresolved Requirements must not be executed as a completed state transition.

## Actions

Identity V1 defines the following Actions:

```text
CREATE_ASSET
CREATE_BLOB
CREATE_SOURCE
UPDATE_SOURCE
DEACTIVATE_SOURCE
```

### CREATE_ASSET

Creates a new long-lived semantic identity.

### CREATE_BLOB

Creates a new immutable content state belonging to an Asset.

### CREATE_SOURCE

Creates a Provider-specific existence and links it to an Asset and Blob.

### UPDATE_SOURCE

Updates mutable Provider-facing state such as path, name, metadata, version tag, active Blob, or related Source properties.

### DEACTIVATE_SOURCE

Marks a Source as no longer present in Provider reality while preserving its historical record.

## Responsibilities

A Decision is responsible for:

- expressing a complete intended state transition;
- preserving the separation between business meaning and persistence;
- carrying domain entities required by each Action;
- reporting unsatisfied evidence requirements.

## Does NOT

A Decision does not:

- access Providers;
- query the World Model;
- calculate evidence;
- execute database operations;
- coordinate transaction order;
- invent Actions independently of Identity.

## Execution Contract

The Repository executes Actions in the order supplied by the Decision.

This order may be significant. For example:

```text
CREATE_ASSET
CREATE_BLOB
CREATE_SOURCE
```

must preserve foreign-key dependencies.

The Repository owns persistence and transaction behavior, but it must not reinterpret the business meaning of the Decision.

## Invariants

1. Decisions are declarative.
2. Identity is the only component that creates business Decisions.
3. Requirements and Actions have different meanings and must not be conflated.
4. Unresolved Requirements prevent final execution.
5. Action ordering is explicit and preserved.
6. A Decision may contain zero Actions when no change is required.
7. Repository implementations must execute equivalent Decisions with equivalent domain results.

## Future Evolution

Additional Requirement or Action types may be added without changing the architecture, provided that:

- Identity remains responsible for producing them;
- the Sync Engine remains responsible for satisfying Requirements;
- Repository remains responsible for executing Actions;
- World Model invariants remain protected.

## Related Documents

- [05 - Sync Engine](05-sync-engine.md)
- [06 - Identity](06-identity.md)
- [08 - Repository](08-repository.md)
- [11 - Sync Lifecycle](11-sync-lifecycle.md)
