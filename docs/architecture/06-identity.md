# 06 - Identity

## Overview

Identity is the core of PDI.

Providers describe the real world.

PDI describes its own world.

Identity is responsible for translating changes in the real world into changes in the PDI world.

It is the bridge between Reality and the World Model.

```
Reality
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
 World Model
```

Identity does **not** store data.

Identity does **not** synchronize files.

Identity only answers one question:

> **"Given what happened in reality, how should the PDI world change?"**

---

# Responsibilities

Identity is responsible for:

- understanding ProviderFacts
- comparing reality with the current PDI world
- requesting additional information when necessary
- generating Decisions

Identity is **not** responsible for:

- reading Providers directly
- writing databases
- calculating hashes
- downloading files

---

# Inputs

Identity receives two things.

## ProviderFact

The current observation from a Provider.

Example:

```
provider = nextcloud

external_id = 12345

path = /docs/a.md

version_tag = abc123
```

ProviderFacts describe reality.

---

## Repository

Identity can query the current PDI world.

For example:

```
Find Source

Find Blob

Find Asset
```

Identity compares:

```
Reality

↓

Current World
```

---

# Requirements

Sometimes ProviderFacts are not sufficient.

Example:

```
version_tag changed
```

Identity cannot determine whether:

- the content changed
- only metadata changed

Therefore Identity returns:

```
Requirement

↓

CONTENT_HASH
```

SyncEngine satisfies the Requirement.

```
ProviderFact

↓

Identity

↓

Requirement(CONTENT_HASH)

↓

SyncEngine

↓

adapter.open()

↓

SHA256

↓

ProviderFact(content_hash)

↓

Identity
```

Identity never downloads files.

Identity never computes hashes.

---

# Decisions

Identity never modifies the database.

Instead it generates Decisions.

A Decision contains Actions.

Example:

```
CREATE_ASSET

CREATE_BLOB

CREATE_SOURCE

UPDATE_SOURCE
```

Repository executes Decisions.

---

# World State Transition

Identity is not simply matching objects.

Identity interprets reality.

It converts real-world changes into world-state transitions.

For example:

Reality:

```
New file
```

↓

Decision:

```
CREATE_ASSET

CREATE_BLOB

CREATE_SOURCE
```

---

Reality:

```
File renamed
```

↓

Decision:

```
UPDATE_SOURCE
```

---

Reality:

```
File moved
```

↓

Decision:

```
UPDATE_SOURCE
```

---

Reality:

```
File content changed
```

↓

Decision:

```
CREATE_BLOB

UPDATE_SOURCE
```

---

Reality:

```
Same content copied
```

↓

Decision:

```
CREATE_SOURCE
```

The new Source references the existing Blob.

No new Blob is created.

---

# Identity Rules

Identity always follows these principles.

## Rule 1

Provider defines reality.

PDI never guesses reality.

---

## Rule 2

Identity only generates Decisions.

It never performs Actions.

---

## Rule 3

Repository is trusted as the source of truth.

Identity compares ProviderFacts against the Repository.

---

## Rule 4

Hash is expensive.

Identity always prefers lightweight metadata first.

```
version_tag

↓

if unchanged

↓

Done

↓

if changed

↓

Request CONTENT_HASH
```

---

## Rule 5

Hash represents content.

VersionTag represents the Provider's version.

They are different concepts.

Hash answers:

> Has the content changed?

VersionTag answers:

> Does the Provider believe this object changed?

Therefore:

```
VersionTag changed

↓

Hash unchanged

↓

UPDATE_SOURCE
```

---

```
VersionTag changed

↓

Hash changed

↓

CREATE_BLOB

+

UPDATE_SOURCE
```

---

# Identity in PDI

Identity is the most important layer of PDI.

Providers observe reality.

Repository stores the PDI world.

Identity explains reality.

Decision describes how the world should evolve.

Without Identity, PDI would only be a synchronization tool.

With Identity, PDI becomes a persistent digital world model.