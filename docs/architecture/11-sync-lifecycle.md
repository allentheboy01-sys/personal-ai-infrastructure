# 11 - Sync Lifecycle

**Status:** Stable for Identity V1

## Purpose

This document describes one complete synchronization session from Provider connection to World Model reconciliation.

Component documents define responsibilities. This document defines the cross-component sequence.

## Session Scope

One synchronization session:

- targets one Adapter;
- represents one Provider identity;
- processes observations from one Provider scan;
- may request additional evidence;
- executes resulting Decisions;
- reconciles missing Sources only after scan completion.

A single session must not mix observations from multiple Provider identities.

## Lifecycle

```text
Start Session
    │
    ▼
Connect Adapter
    │
    ▼
Begin Provider Scan
    │
    ▼
Receive ProviderFact
    │
    ▼
Identity Match
    │
    ├── Requirement present?
    │        │
    │        ▼
    │   Satisfy Requirement
    │        │
    │        ▼
    │   Enrich ProviderFact
    │        │
    │        └──────► Identity Match
    │
    ▼
Execute Decision
    │
    ▼
Repeat for all Facts
    │
    ▼
Complete Scan Successfully
    │
    ▼
Reconcile Active Sources
    │
    ▼
Deactivate Missing Sources
    │
    ▼
Finish Session
```

## Phase 1: Connection

The Sync Engine connects through the Adapter.

A connection failure ends the session. No absence inference or reconciliation may occur.

## Phase 2: Scan

The Adapter emits normalized `ProviderFact` objects.

During the scan, the Sync Engine records the Provider external identities observed in the session.

Each fact must identify the same Provider identity for the entire run.

## Phase 3: Identity Evaluation

For each fact, Identity compares Provider reality with the current World Model.

Identity may return:

- an executable Decision;
- a Decision with Requirements;
- an empty Decision when no change is required.

## Phase 4: Requirement Loop

When Identity requires additional evidence, the Sync Engine coordinates its collection.

Current example:

```text
Requirement(CONTENT_HASH)
    │
    ▼
Adapter.open()
    │
    ▼
SHA-256 Capability
    │
    ▼
ProviderFact + content_hash
    │
    ▼
Identity
```

The loop continues until:

- all Requirements are satisfied and an executable Decision is produced; or
- a Requirement cannot be satisfied and the fact fails safely.

A Decision with unresolved Requirements must not be treated as a completed transition.

## Phase 5: Decision Execution

The Repository executes the Decision transactionally.

Each fact's Decision is applied according to explicit Action order. A failed execution must roll back that Decision.

The current session does not guarantee one database transaction across the entire Provider scan. Transaction scope is the executed Decision unless explicitly changed by a later architecture version.

## Phase 6: Scan Completion

Reconciliation is allowed only when the Adapter scan completes successfully.

A partial scan, connection failure, iteration error, or aborted session must not be interpreted as Provider deletion.

This rule prevents accidental mass deactivation.

## Phase 7: Reconciliation

After a complete scan, the Sync Engine compares:

```text
Active Sources previously stored for Provider
                    −
Provider external identities observed in this scan
                    =
Missing Sources
```

For each missing Source, Identity produces:

```text
DEACTIVATE_SOURCE
```

The Repository executes the Decision, setting the Source inactive and preserving its historical record.

## Difference Ownership

The scan-level difference belongs to the synchronization lifecycle, not to per-fact Identity matching.

Identity understands the meaning of deactivation. The Sync Engine owns the complete-scan context required to determine which Sources are missing.

The Repository only provides queries and executes Decisions.

## Failure Rules

1. Connection failure stops the session.
2. Scan failure stops the session.
3. A failed or partial scan never triggers reconciliation.
4. Provider identity inconsistency stops the session.
5. Unresolved Requirements prevent execution for the affected fact.
6. Repository failure rolls back the affected Decision.
7. Source absence is inferred only from a successful complete scan.

## Observability

A synchronization session should expose enough structured logging to identify:

- session start and completion;
- Adapter connection;
- scan start and completion;
- facts processed;
- Requirements requested and satisfied;
- Actions executed;
- missing Sources detected;
- Sources deactivated;
- duration and failure location.

Observability does not change business meaning, but it is required for safe operation and diagnosis.

## Current Boundary

Identity V1 lifecycle supports:

- one Provider per session;
- complete scan processing;
- per-fact matching;
- content-hash requirement resolution;
- Decision execution;
- post-scan reconciliation;
- Source deactivation;
- structured progress logging.

It does not yet define:

- incremental checkpoints;
- automatic retry policy;
- resume after interruption;
- parallel Provider synchronization;
- cross-session conflict resolution;
- Source reactivation;
- one atomic transaction for an entire scan;
- scheduler behavior.

## Related Documents

- [03 - Provider Adapter](03-provider-adapter.md)
- [05 - Sync Engine](05-sync-engine.md)
- [06 - Identity](06-identity.md)
- [07 - Decision](07-decision.md)
- [08 - Repository](08-repository.md)
