# 09 - World Model

## Status

V0.2 Frozen for Create and Update.

Source deactivation and full-scan reconciliation are not yet implemented.

## Core Idea

PDI does not copy Provider databases.

PDI builds and maintains its own persistent World Model from observations made by Providers.

Providers describe their current reality.

PDI interprets that reality and preserves its own understanding and history.

```text
Provider Reality
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
Repository
        │
        ▼
PDI World Model
```

The World Model is independent of:

- any single Provider
- any single database implementation
- any AI model
- Jarvis
- any user interface

---

## Core Entities

PDI V0.2 currently contains three core entities:

```text
Asset
  │
  ▼
Blob
  │
  ▼
AssetSource
```

Their responsibilities are different.

```text
Asset       = long-lived semantic identity
Blob        = one concrete content state
AssetSource = one Provider-specific existence of that content
```

---

## Asset

Asset is the long-lived semantic identity of a digital object.

It answers:

> What is this digital object in the PDI world?

Asset is not:

- a file path
- a Provider record
- a content hash
- a physical file
- a temporary scan result

Examples may include:

- a document
- a photograph
- a video
- an email
- a message
- a Git object

An Asset can remain the same while its content changes.

Example:

```text
Asset: Project Proposal
├── Blob V1
├── Blob V2
└── Blob V3
```

The Asset represents the continuing identity.

The Blobs represent its content states.

---

## Blob

Blob is an immutable content unit.

It answers:

> What exact content did this Asset have?

Blob is primarily identified by its content hash.

A Blob may contain:

- document bytes
- image bytes
- video bytes
- message body content
- other immutable digital content

One Asset may have multiple Blobs over time.

Example:

```text
Asset: identity-renamed.txt
├── Blob V1: SHA-256 A
└── Blob V2: SHA-256 B
```

When content changes:

```text
CREATE_BLOB
+
UPDATE_SOURCE
```

The old Blob remains in the World Model.

This preserves the fact that the Asset previously had that content.

A Blob is not modified in place.

---

## AssetSource

AssetSource represents one Provider-specific existence of a Blob.

It answers:

> Where does this content currently exist in the Provider world?

An AssetSource contains information such as:

- provider
- external_id
- path
- name
- version_tag
- metadata
- blob_id

Example:

```text
Asset
└── Blob
    ├── AssetSource: Nextcloud / identity-renamed.txt
    └── AssetSource: Nextcloud / identity-copy.txt
```

Both Sources may point to the same Blob when the files have identical content.

AssetSource identity is determined by:

```text
provider + external_id
```

Path and name are properties, not identity.

Therefore:

```text
rename
→ UPDATE_SOURCE
```

and:

```text
move
→ UPDATE_SOURCE
```

rather than creating a new Source.

---

## Current Source and Historical Blob

AssetSource points to the currently confirmed Blob for that Provider object.

Example:

```text
Before content update:

Asset
├── Blob V1
│    ▲
│    └── Source
```

After content update:

```text
Asset
├── Blob V1
└── Blob V2
     ▲
     └── Source
```

Blob V1 remains as historical content.

The Source now points to Blob V2.

PDI currently preserves historical Blobs but does not yet record a complete temporal history such as:

- when each Blob became current
- when it stopped being current
- the exact sequence of Source-to-Blob transitions

That may later be represented through a timeline, decision log, or source-history model.

---

## ProviderFact

ProviderFact is a normalized observation produced by an Adapter.

It represents a snapshot of Provider reality at one moment.

ProviderFact is not part of the persistent World Model.

It does not directly become a database row.

It must pass through Identity.

```text
Provider
    │
    ▼
Adapter
    │
    ▼
ProviderFact
    │
    ▼
Identity
```

ProviderFact contains normalized information such as:

- provider
- external_id
- kind
- name
- attributes
- raw Provider metadata

Provider-specific raw information may be preserved in:

```text
AssetSource.metadata
```

---

## Identity

Identity interprets the difference between:

```text
current ProviderFact
```

and:

```text
current PDI World Model
```

It generates a Decision.

Identity does not modify the database directly.

Current supported transitions are:

### New Source and new content

```text
CREATE_ASSET
CREATE_BLOB
CREATE_SOURCE
```

### New Source with existing content

```text
CREATE_SOURCE
```

The new Source points to an existing Blob.

### Existing Source unchanged

```text
No Action
```

### Existing Source metadata, path, or name changed

```text
UPDATE_SOURCE
```

### Existing Source content changed

```text
CREATE_BLOB
UPDATE_SOURCE
```

The Source remains the same identity but points to a new Blob.

---

## Sync Engine

SyncEngine is the orchestration layer.

It is responsible for:

- connecting to the Adapter
- streaming ProviderFacts
- passing each Fact to Identity
- satisfying Requirements such as `CONTENT_HASH`
- executing Decisions through Repository
- recording synchronization progress

SyncEngine does not decide whether something is:

- a new Asset
- a new Blob
- the same Source
- an updated Source

Those are Identity decisions.

Current flow:

```text
Adapter.connect()
        │
        ▼
Adapter.scan()
        │
        ▼
ProviderFact
        │
        ▼
Identity.match()
        │
        ├── Requirement(CONTENT_HASH)
        │          │
        │          ▼
        │     Adapter.open()
        │          │
        │          ▼
        │     Calculate SHA-256
        │          │
        └──────────┘
        │
        ▼
Decision
        │
        ▼
Repository.execute()
```

---

## Repository

Repository is the persistence boundary of the World Model.

It provides Identity with access to the current PDI state and executes Decisions.

Current Repository operations include:

- find Source by Provider identity
- find Blob by hash
- find Blob by hash within an Asset
- retrieve Blob
- retrieve Asset
- execute Decision transactionally

Repository does not decide business meaning.

It trusts Decisions generated by Identity.

---

## Source Lifecycle

Current implemented Source lifecycle:

```text
CREATE_SOURCE
UPDATE_SOURCE
```

Planned next stage:

```text
DEACTIVATE_SOURCE
```

A deleted Provider object should not cause the Source record to be physically removed.

Instead, PDI should preserve its historical existence and mark it inactive.

Planned fields include:

```text
is_active
deleted_at
```

This feature requires a complete successful Provider scan followed by reconciliation.

It is not yet implemented in V0.2.

---

## Current Boundaries

PDI V0.2 does not yet include:

- recursive Nextcloud folder scanning
- Source deactivation
- full-scan reconciliation
- Source reactivation
- complete Source-to-Blob temporal history
- Collection as a first-class entity
- Metadata as an independent entity
- abstract life events as Assets
- automatic semantic merging of different formats

These are future capabilities and should not be assumed by the current World Model.

---

## Design Principles

### Asset is semantic identity

Asset survives content changes.

### Blob is immutable content

Content changes create new Blobs.

### Source is Provider existence

Rename and move update Source properties without changing its identity.

### Provider identity is stable

```text
provider + external_id
```

defines a Source.

### History is preserved

Old Blobs are retained when the current Source moves to a new Blob.

### World Model is independent

PDI does not mirror a Provider database and does not belong to an AI model.