# 09 - World Model

**Status:** Stable for Identity V1

## Purpose

The World Model is PDI's persistent, Provider-independent representation of a person's digital life.

PDI does not mirror Provider databases. Providers report observations; PDI interprets those observations and maintains its own stable identities, content states, Provider existences, and history.

## Independence

The World Model is independent of:

- any single Provider;
- any single database implementation;
- any AI model or agent;
- Jarvis;
- any user interface;
- Provider-specific paths, schemas, or APIs.

Providers, applications, storage engines, and AI systems may be replaced without redefining the World Model.

## Core Entities

Identity V1 uses three persistent domain entities:

```text
Asset
  │
  ├── Blob
  │     ▲
  │     │
  └── AssetSource
```

Their meanings are distinct:

```text
Asset       = long-lived semantic identity
Blob        = one immutable content state
AssetSource = one Provider-specific existence
```

## Asset

An `Asset` is the stable identity of a digital object in PDI.

It answers:

> What is this object in the PDI world?

An Asset is not:

- a file path;
- a Provider record;
- a content hash;
- a physical storage location;
- a temporary scan result.

An Asset may survive:

- renames;
- moves;
- Provider changes;
- content changes;
- temporary Source disappearance.

One Asset may contain multiple historical Blobs.

```text
Asset: Project Proposal
├── Blob V1
├── Blob V2
└── Blob V3
```

## Blob

A `Blob` is one immutable content state belonging to an Asset.

It answers:

> What exact content did this Asset have?

A Blob is primarily identified by content evidence such as a cryptographic hash.

When content changes, PDI creates a new Blob rather than mutating the existing Blob.

```text
Before
Asset
└── Blob V1
     ▲
     └── Source

After
Asset
├── Blob V1
└── Blob V2
     ▲
     └── Source
```

The old Blob remains part of the Asset's preserved history.

Identical content may be shared by multiple Sources without creating duplicate Blobs.

## AssetSource

An `AssetSource` represents one Provider-specific existence of digital content.

It answers:

> Where and under which Provider identity does this object currently exist?

A Source carries Provider-facing state such as:

- `provider`;
- `external_id`;
- `path`;
- `name`;
- `version_tag`;
- Provider metadata;
- current `blob_id`;
- active state;
- deletion timestamp.

Source identity is:

```text
provider + external_id
```

Path and name are mutable properties. Rename and move operations update the existing Source.

A Source points to the currently confirmed Blob for that Provider object. When content changes, the Source moves to a new Blob while the previous Blob remains historical.

## Source Lifecycle

Identity V1 supports the following Source lifecycle:

```text
CREATE_SOURCE
    │
    ▼
UPDATE_SOURCE
    │
    ▼
DEACTIVATE_SOURCE
```

A Source is deactivated only after a successful complete scan establishes that its Provider identity was not observed.

Deactivation is a soft-delete operation:

```text
is_active = false
deleted_at = timestamp
```

The Source row is retained. PDI preserves the fact that the Source previously existed.

Source reactivation is not yet defined by Identity V1.

## ProviderFact Boundary

A `ProviderFact` is not part of the World Model.

It is a temporary observation used during synchronization:

```text
Provider reality
    │
    ▼
ProviderFact
    │
    ▼
Identity
    │
    ▼
Decision
    │
    ▼
World Model
```

ProviderFacts do not become persistent rows directly. All persistent change must pass through Identity and Decision.

## History Model

Identity V1 preserves:

- previous Blobs after content changes;
- inactive Sources after Provider disappearance;
- stable Asset identity across Source changes.

Identity V1 does not yet preserve a complete temporal event log showing:

- exactly when each Blob became current;
- exactly when a Source changed from one Blob to another;
- every Decision that produced a transition;
- Source reactivation intervals.

Those concerns may later be represented by a timeline, event log, or dedicated history model.

## Invariants

1. Assets represent stable semantic identity.
2. Blobs represent immutable content states.
3. Sources represent Provider-specific existence.
4. Source identity is `provider + external_id`.
5. Path and name do not define identity.
6. Content changes create new Blobs.
7. Existing Blobs are never modified in place.
8. Identical content may reuse an existing Blob.
9. Source disappearance causes deactivation, not physical deletion.
10. Missing objects are inferred only after a successful complete scan.
11. ProviderFacts are temporary observations, not persistent entities.
12. Providers do not directly define or mutate the World Model.
13. AI may consume or propose interpretations, but it does not define core World Model invariants.

## Current Boundary

The current World Model does not yet define first-class:

- Relations;
- Tags;
- Evidence;
- Collections;
- life events;
- complete transition history;
- semantic merging across different representations;
- Source reactivation.

These may be introduced only when their abstractions reduce overall system complexity and their invariants are explicitly defined.

## Related Documents

- [01 - Architecture Overview](01-overview.md)
- [04 - Provider Fact](04-provider-fact.md)
- [06 - Identity](06-identity.md)
- [08 - Repository](08-repository.md)
- [11 - Sync Lifecycle](11-sync-lifecycle.md)
