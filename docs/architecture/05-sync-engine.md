# 05 - Sync Engine

**Status:** Stable for Identity V1

## Purpose

The Sync Engine owns the execution lifecycle of one synchronization session between one Provider Adapter and the PDI World Model.

It coordinates existing components without making identity decisions or implementing storage rules.

## Responsibilities

The Sync Engine is responsible for:

- connecting to one Adapter;
- starting and completing one Provider scan;
- passing each `ProviderFact` to Identity;
- satisfying declared Requirements through the appropriate Adapter and Capability;
- returning enriched facts to Identity for another decision pass;
- executing complete Decisions through the Repository;
- recording the external identifiers observed during a complete scan;
- reconciling active Sources that were not observed;
- emitting synchronization progress and outcome logs.

## Session Boundary

One synchronization session represents one Provider identity. Facts from multiple Providers must not be mixed in the same run.

Missing-object reconciliation is valid only after a complete successful scan
whose required per-fact reads all resolved. A failed, partial, or otherwise
non-authoritative scan must never deactivate Sources merely because they were
not observed.

Discovery has two explicit run-level modes. `FULL_AUTHORITATIVE` may infer
missing Sources only when the entire run remains reconciliation-safe.
`INCREMENTAL_NON_AUTHORITATIVE` never infers deletion from absence: a Source
missing from one change batch remains active. Discovery mode, checkpoints, and
deletion evidence are batch mechanics and never fields on `ProviderFact`.

Authority is relative to the observation scope defined by the configured
Adapter connection. A complete traversal can be authoritative for a credential,
account, tenant, folder, or permission scope without claiming access to all
data physically stored behind the Provider.

Incremental checkpoints belong to PDI operational persistence in the dedicated
`provider_sync_state` table. The engine reads state before discovery, applies
all facts and any future qualified tombstones durably, then advances the opaque
checkpoint with compare-and-swap as the final write. A failure before that CAS
may leave facts committed and the checkpoint unchanged; replaying the same
window is intentional and identity-safe. Invalid or uninterpretable state is
marked `reconciliation_required` and blocks further incremental discovery
until a future full reconciliation restores trust.

A `NULL` checkpoint means only that no trusted checkpoint has been established.
Normal advancement requires a non-empty opaque checkpoint and cannot erase a
trusted checkpoint. Recovery is a separate CAS operation: after a caller has
independently proven a successful full reconciliation and acquired a fresh
Provider-specific bootstrap checkpoint, it may atomically install that trusted
checkpoint and clear `reconciliation_required`. A full scan alone never clears
the latch automatically.

Immich v3.1 is the first Provider-specific use of this boundary. Its
`metadata_updated_at_v1` mechanism stores a canonical UTC timestamp and queries
the stable metadata search endpoint from checkpoint minus five minutes through
a run-start upper bound. The overlap and inclusive timestamp boundaries make
replay intentional. Initial bootstrap and reconciliation recovery capture a
fresh anchor before a successful full authoritative scan and install it last.
Incremental absence is never scope-exit evidence; periodic full reconciliation
is required to converge Sources that leave the configured observation scope.
Immich v3.1 reports `total` and `count` for the current page, not for the global
query. PDI validates those values only against that page's item count. Because
the API uses offset pagination without snapshot isolation, PDI traverses the
same fixed query twice and requires the ordered asset-ID sequences to match.
Duplicate IDs within either pass or a cross-pass mismatch fail discovery
without advancing the checkpoint or marking checkpoint state invalid. This is
fail-closed consistency evidence, not an atomic snapshot.

Immich V0.1 synchronizes the configured API key's visible metadata-search
scope. It does not promise enumeration of Locked assets and does not attempt an
elevated session, PIN handling, or direct database access. A stable full-scope
absence deactivates the Source, but does not classify why it became absent:
permanent deletion, Locked visibility, permissions, sharing, or another scope
change have the same observable result. If the same Provider identity returns
to scope, Identity reactivates its existing Source. Soft-trash assets returned
through `withDeleted=true` remain active Provider resources.

Adapters may stream facts. Valid per-fact Decisions may therefore commit before
the traversal completes, but those commits do not make the provider snapshot
authoritative.

## Requirement Loop

```text
ProviderFact
    │
    ▼
Identity
    │
    ├── Decision(actions)
    │
    └── Decision(requirements)
              │
              ▼
       Adapter / Capability
              │
              ▼
       enriched ProviderFact
              │
              └──────► Identity
```

The Sync Engine executes no Decision while unresolved Requirements remain.

## Reconciliation

After a complete scan, the Sync Engine compares:

```text
active Sources already in PDI
-
external identifiers observed in this scan
=
missing Sources
```

Each missing Source is passed through the defined deactivation path and persisted as inactive. It is not physically deleted.

If an observed resource disappears while satisfying a content requirement, the
Sync Engine skips the unresolved fact and may continue processing later facts.
The run remains non-authoritative, performs no missing-source reconciliation,
and fails after traversal with a sanitized incomplete-sync error.

## Does NOT

This foundation does not implement Nextcloud Activity discovery, Immich
timestamp discovery, Provider-specific tombstone qualification, or automatic
incremental scheduling.

The Sync Engine does not:

- decide whether content represents a new or existing Asset;
- interpret Provider-specific fields;
- calculate business meaning;
- define World Model entities;
- write storage directly;
- schedule itself continuously;
- treat an incomplete scan as authoritative absence.

## Related Documents

- [06 - Identity](06-identity.md)
- [08 - Repository](08-repository.md)
- [11 - Sync Lifecycle](11-sync-lifecycle.md)
