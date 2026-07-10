# PDI Current Context

> Snapshot of the current development state.
> Rewritten after every completed milestone.
>
> This document records only the latest project state.
> Git history records how the project reached this state.

---

# Current Stage

Phase:
Core Engineering

Version:
V0.1 Alpha

Current Milestone:
First Real Sync Completed

Current Goal:
Implement persistent World Model storage with PostgreSQL.

---

# Current Progress

## ✅ Infrastructure

- Ubuntu Server
- Docker
- Portainer
- Nextcloud
- Redis
- Python virtual environment
- Git repository
- Environment variable configuration

## ✅ Adapter Layer

- Adapter base interface
- Adapter registry
- Nextcloud Adapter
- WebDAV connection
- WebDAV metadata scan
- Stable Nextcloud identity through `oc:id`
- Chunked content reading through `Adapter.open()`
- Provider-specific normalization into `ProviderFact`

## ✅ Capability Layer

- SHA-256 content hashing
- Chunk-based hashing without loading the complete file into memory

## ✅ World Model

- Asset
- Blob
- AssetSource
- AssetSource version tag
- Stable internal UUID identities

## ✅ Decision Model

- Decision
- Action
- ActionType
- RequirementType
- Content Hash Requirement

## ✅ Identity

- Matcher V0.1
- ProviderFact validation
- New Source recognition
- Existing Source recognition
- Rename and path-change recognition
- Immutable Blob history
- Cross-Provider Blob reuse for new Sources
- Asset lifecycle continuity for existing Sources

## ✅ Repository

- Repository interface
- InMemoryRepository
- Decision execution
- World Model queries
- Asset-scoped Blob lookup

## ✅ Sync Engine

- One-time synchronization workflow
- Requirement handling
- On-demand content download
- SHA-256 calculation
- Re-entry into Matcher after satisfying requirements
- Decision execution through Repository

## ✅ Testing

Six Matcher scenarios are covered by automated tests:

1. New Source and new Blob
2. Repeated synchronization with no change
3. Rename or path change
4. Content change creating a new Blob
5. New Source reusing an existing Blob
6. Existing Source remaining inside its original Asset lifecycle

All current tests pass.

## ✅ Real Integration

The following real pipeline has been successfully executed:

```text
Nextcloud
→ Nextcloud Adapter
→ ProviderFact
→ Matcher
→ Content Hash Requirement
→ Sync Engine
→ Adapter.open()
→ SHA-256 Capability
→ Matcher
→ Decision
→ InMemoryRepository
→ Asset / Blob / AssetSource
```

A real Nextcloud root scan successfully imported:

- 6 Assets
- 6 Blobs
- 6 AssetSources

Folders are intentionally ignored in V0.1.

## ⏳ In Progress

- Milestone documentation
- Git commit and GitHub synchronization

## ⬜ Not Started

- PostgreSQL schema
- PostgreSQLRepository
- SQLAlchemy models
- Database migrations
- Persistent incremental synchronization
- Sync retry and failure records
- Additional Providers
- Relation
- Event
- Timeline
- Collection
- Query API
- Rule Engine
- AI Interface

---

# Frozen Architecture

The current V0.1 execution flow is:

```text
Provider
→ Adapter
→ ProviderFact
→ Sync Engine
→ Matcher
→ Decision
```

The Decision may contain:

```text
Requirements
→ fulfilled by Sync Engine and Capabilities

Actions
→ executed by Repository
```

The persistent flow will eventually be:

```text
Provider
→ Adapter
→ ProviderFact
→ Sync Engine
→ Matcher
→ Decision
→ Repository
→ PostgreSQL
→ World Model
```

---

# Frozen Domain Model

## Asset

Asset represents the lifetime of one semantic digital object.

Examples:

- A thesis
- A photograph
- A message
- A document

Asset is the smallest semantic unit in V0.1.

Asset is not:

- A folder
- A collection
- A project
- An album

Asset creation rule:

> Create a new Asset when a new Blob cannot be assigned to an existing Asset.

Asset lifecycle rules:

- Asset does not end automatically.
- Asset is not split in V0.1.
- Asset merging may be supported later.
- User-controlled deletion may be supported later.

---

## Blob

Blob represents one immutable content snapshot.

Rules:

- Blob is not a file location.
- Blob is never updated.
- Any content change creates a new Blob.
- Blob has its own internal UUID.
- Content Hash is a fingerprint, not the Blob identity.
- Two Blobs may have the same Hash while belonging to different Assets.
- Each Blob belongs to exactly one Asset.

Relationship:

```text
Asset
1 → N
Blob
```

---

## AssetSource

AssetSource represents one current Provider-side existence of a Blob.

Examples:

- One Nextcloud file
- One Google Drive object
- One local file
- One message inside a messaging Provider

Rules:

- AssetSource points to exactly one Blob.
- AssetSource does not store `asset_id`.
- Asset membership is derived through Blob.
- Provider and external ID identify the Source.
- Path and name are mutable Source properties.
- Version tag is Provider-specific state.
- Content changes update the Source to point to another Blob.
- Rename and move operations do not create a new Blob.

Relationship:

```text
Blob
1 ← N
AssetSource
```

---

# Frozen Adapter Rules

Adapter responsibilities:

- Communicate with one Provider
- Authenticate with the Provider
- Scan Provider objects
- Normalize Provider data
- Read content on demand

Current Adapter interface:

```text
connect()
scan()
open(fact)
```

Adapter must not:

- Make Asset identity decisions
- Write the World Model
- Execute database operations
- Contain Repository logic

---

# Frozen ProviderFact Rules

ProviderFact is the normalized result of one Provider scan.

ProviderFact is:

- Temporary
- Produced by Adapter
- Consumed during one synchronization cycle
- Never written directly into the World Model database

Top-level fields represent common identity information.

`attributes` contains normalized optional properties.

`raw` contains Provider-specific data and must not be consumed by Matcher.

Current normalized file properties include:

- path
- size
- mime type
- modified time
- version tag
- content hash

For Nextcloud:

- `oc:id` is used as stable `external_id`
- WebDAV `href` remains Provider-specific raw data
- ETag is normalized as `version_tag`
- ETag is not treated as content Hash

---

# Frozen Identity Rules

Matcher input:

```text
ProviderFact
+
Repository
```

Matcher output:

```text
Decision
```

Matcher responsibilities:

- Validate ProviderFact
- Query the current World Model
- Request missing information
- Decide which World Model actions are required

Matcher must not:

- Call Adapter
- Download content
- Calculate Hash
- Write the database
- Retry network operations

Current matching rules:

```text
New Source + new content
→ CREATE_ASSET
→ CREATE_BLOB
→ CREATE_SOURCE
```

```text
New Source + existing Blob
→ CREATE_SOURCE
```

```text
Existing Source + unchanged state
→ No Action
```

```text
Existing Source + renamed or moved
→ UPDATE_SOURCE
```

```text
Existing Source + new content
→ CREATE_BLOB
→ UPDATE_SOURCE
```

Existing Sources must remain inside their original Asset lifecycle.

A global Hash match must not move an existing Source into another Asset.

---

# Frozen Decision Rules

Decision is a structured result produced by Matcher.

Decision contains:

```text
requirements
actions
reason
confidence
```

Requirements represent missing information.

Current Requirement:

```text
CONTENT_HASH
```

Actions represent World Model changes.

Current Actions:

```text
CREATE_ASSET
CREATE_BLOB
CREATE_SOURCE
UPDATE_SOURCE
```

Decision does not execute itself.

---

# Frozen Repository Rules

Repository is the access and execution interface for the World Model.

Repository is not:

- A Provider Adapter
- Identity logic
- A simple DAO
- PostgreSQL itself

Repository responsibilities:

- Query the current World Model
- Execute Decisions
- Store and retrieve domain objects
- Hide the physical storage implementation

Current implementation:

```text
InMemoryRepository
→ Python dictionaries
```

Future implementation:

```text
PostgreSQLRepository
→ PostgreSQL
```

Matcher and Sync Engine must not change when the storage implementation changes.

---

# Frozen Sync Engine Rules

Sync Engine is a workflow coordinator.

It does not make identity decisions.

Current responsibilities:

1. Connect to Adapter
2. Scan ProviderFacts
3. Send each Fact to Matcher
4. Read Decision requirements
5. Fulfil supported requirements
6. Return the enriched Fact to Matcher
7. Execute final actions through Repository

Current public operation:

```text
sync_once()
```

Scheduling, continuous watching and recurring execution do not belong to Sync Engine.

---

# Error Handling Direction

One failed object must not stop the entire synchronization cycle.

Future errors will be classified as:

```text
Retryable
- Network timeout
- Temporary Provider failure
- Interrupted content reading
- Rate limiting

Non-retryable
- Invalid ProviderFact
- Missing stable identity
- Unsupported object type
- Permanent permission failure
```

Retry logic belongs to Sync Engine or a surrounding execution layer.

Matcher does not retry operations.

Failed objects must not be silently discarded.

This behavior is not implemented yet.

---

# Current Repository Structure

```text
PDI/

├── adapters/
│   ├── base.py
│   ├── registry.py
│   └── nextcloud/
├── capability/
│   └── hash.py
├── decision/
│   ├── action.py
│   ├── decision.py
│   └── requirement.py
├── engine/
│   └── sync_engine.py
├── identity/
│   └── matcher.py
├── models/
│   ├── asset.py
│   ├── blob.py
│   └── asset_source.py
├── repository/
│   ├── base.py
│   └── memory.py
├── tests/
│   └── test_matcher.py
├── docs/
├── main.py
└── pyproject.toml
```

---

# Current Limitation

The current World Model is stored only in memory.

Therefore:

- Data disappears when the Python process ends.
- Every `python main.py` run starts from an empty World Model.
- Persistent incremental synchronization cannot yet be verified.
- PostgreSQL persistence is the next required milestone.

---

# Next Milestone

## PostgreSQL Persistence

Goal:

Replace the in-memory storage implementation with PostgreSQL without modifying:

- Nextcloud Adapter
- ProviderFact
- Matcher
- Decision
- Sync Engine

Expected outputs:

- PostgreSQL schema
- SQLAlchemy dependency
- SQLAlchemy persistence models
- Database connection configuration
- PostgreSQLRepository
- Database initialization or migration process
- Repository behavior tests
- Persistent second synchronization producing no duplicate objects

Success condition:

```text
First run:
Create Assets, Blobs and Sources

Second unchanged run:
Create no duplicate Assets, Blobs or Sources
```

---

# Important Principles

- Architecture First
- Every abstraction must justify its existence
- Prefer removing abstractions over adding unnecessary layers
- Asset represents lifetime
- Blob is immutable
- AssetSource represents Provider-side existence
- ProviderFact is transient
- Identity decides
- Decision describes
- Repository executes
- Sync Engine coordinates
- Capability produces missing information
- Provider-specific details must not leak into Matcher
- AI must remain replaceable
- Provider must remain replaceable
- Database must remain replaceable
- Git records development history
- CURRENT_CONTEXT records only the latest snapshot
- When code and documentation conflict, inspect and verify the repository

---

# Intentionally Postponed

The following concepts are outside V0.1 Core:

- Folder modeling
- Collection
- Relation
- Event
- Timeline
- Knowledge Graph
- Merge workflow
- Conflict resolution
- OCR
- EXIF extraction
- Embeddings
- AI-generated semantic titles
- AI Memory
- Multi-Provider synchronization