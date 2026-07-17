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

Missing-object reconciliation is valid only after a complete successful scan. A failed or partial scan must never deactivate Sources merely because they were not observed.

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

## Does NOT

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
