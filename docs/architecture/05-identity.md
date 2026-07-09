# 05 - Identity

**Status:** V0.1 Draft

---

## Purpose

Identity decides how new ProviderFacts should affect the PDI World Model.

Identity does not classify files.

Identity reconciles Provider reality with the PDI World Model.

---

## Input

Identity Matcher has two inputs:

1. New ProviderFact
2. Existing World Model

Existing World Model includes:

- Asset
- Blob
- AssetSource

---

## Output

Identity Matcher does not directly write the database.

It produces a Decision.

The Repository applies that Decision to the database.

---

## Flow

    ProviderFact
        ↓
    Evidence
        ↓
    Decision
        ↓
    Repository
        ↓
    Asset / Blob / AssetSource

---

## Evidence

Evidence is the objective information used to support a decision.

Examples:

- provider
- external_id
- name
- path
- size
- mime_type
- hash
- etag
- modified_at

Evidence answers:

> Why did PDI make this decision?

---

## Decision

Decision is the result of Identity matching.

V0.1 decisions:

- update_existing_source
- reuse_blob
- create_new_blob
- create_new_asset
- uncertain

---

## V0.1 Policy

### 1. Source Check

If `provider + external_id` already exists:

    update_existing_source

This means PDI has seen the same Provider object before.

---

### 2. Blob Check

If content hash already exists:

    reuse_blob

This means PDI has seen the same content before.

---

### 3. New Blob

If content hash does not exist:

    create_new_blob

This means PDI has not seen this content before.

---

### 4. Asset Check

If there is not enough evidence to prove that this belongs to an existing Asset:

    create_new_asset

---

### 5. Uncertain

If evidence suggests similarity but confidence is not high enough:

    uncertain

PDI should not automatically merge.

---

## Core Principle

V0.1 prefers duplication over incorrect merging.

It is safer to create two Assets than to wrongly merge two unrelated Assets.

---

## What Identity Does Not Do

Identity does not:

- connect to Providers
- scan files
- download content
- write database directly
- call AI directly
- expose user interaction

---

## Relationship to Other Components

| Component | Responsibility |
|---|---|
| Adapter | Reads ProviderFacts |
| Sync Engine | Detects changes |
| Identity Matcher | Produces Evidence and Decision |
| Repository | Applies Decision to database |
| World Model | Stores Asset, Blob, AssetSource |

---

## Future Evolution

Future versions may support:

- semantic similarity
- OCR comparison
- AI-assisted merge suggestions
- human confirmation workflow
- split / unmerge decisions
- decision history