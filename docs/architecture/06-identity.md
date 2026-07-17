# 06 - Identity

**Status:** Stable for Identity V1

## Purpose

Identity determines how observations from Provider reality should change the PDI World Model.

It compares a `ProviderFact` with the current World Model and produces a `Decision`. Identity is the business-meaning boundary of ingestion: Providers report what they observe, while Identity decides what that observation means inside PDI.

## Core Question

> Given this Provider observation and the current PDI state, what should change?

Identity does not perform the change. It only describes it.

## Inputs

Identity receives:

- one normalized `ProviderFact`;
- read access to the current World Model through the Repository interface.

Identity must not read Provider APIs directly.

## Output

Identity returns a `Decision` containing:

- zero or more `Action` values;
- zero or more `Requirement` values.

A Decision with no actions and no requirements means that the observation does not require a World Model change.

## Responsibilities

Identity is responsible for:

- finding an existing `AssetSource` by `provider + external_id`;
- distinguishing a new Source from an existing Source;
- distinguishing metadata changes from content changes;
- deciding whether a new Asset is required;
- reusing an existing Blob when identical content already exists;
- creating a new Blob when an existing Asset gains a new content state;
- updating a Source when its path, name, metadata, version, or current Blob changes;
- producing source-deactivation Decisions when reconciliation identifies a missing Source;
- requesting additional evidence when the current fact is insufficient.

## Does NOT

Identity does not:

- connect to Providers;
- open or download content;
- calculate hashes;
- coordinate scans;
- determine whether a scan completed successfully;
- write to storage;
- execute Actions;
- define transport or database behavior.

## Source Identity

An `AssetSource` is identified by:

```text
provider + external_id
```

Path and name are mutable properties, not identity.

Therefore, a rename or move updates the existing Source rather than creating a new one.

## Content Identity

A Provider version tag and a content hash answer different questions:

- `version_tag`: does the Provider report that this object changed?
- `content_hash`: is the content actually different?

Identity first uses lightweight Provider metadata. When a changed version tag is not enough to determine content identity, it returns:

```text
Requirement(CONTENT_HASH)
```

The Sync Engine satisfies the requirement and calls Identity again with an enriched fact.

## State Transitions

### New Source with new content

```text
CREATE_ASSET
CREATE_BLOB
CREATE_SOURCE
```

### New Source with existing content

```text
CREATE_SOURCE
```

The Source points to an existing Blob. No duplicate Blob is created.

### Existing Source unchanged

```text
No Action
```

### Existing Source metadata, path, name, or Provider version changed without content change

```text
UPDATE_SOURCE
```

### Existing Source content changed

```text
CREATE_BLOB
UPDATE_SOURCE
```

The Source keeps its identity and points to the new Blob. The previous Blob remains historical content of the Asset.

### Existing Source missing after a successful complete scan

```text
DEACTIVATE_SOURCE
```

The Source is marked inactive and receives a deletion timestamp. It is not physically deleted.

## Invariants

1. Identity produces Decisions; it never performs persistence.
2. A Source identity is stable across rename and move operations.
3. Existing Blobs are immutable.
4. Content changes create new Blobs.
5. Identical content should reuse an existing Blob when the current matching scope permits it.
6. Provider metadata is evidence, not PDI semantic identity.
7. Expensive evidence is requested only when lightweight evidence is insufficient.
8. Missing objects are not inferred from a partial or failed scan.
9. Deactivation preserves history instead of deleting it.
10. Identity decisions must remain independent of the storage implementation.

## Current Boundary

Identity V1 supports:

- new Asset, Blob, and Source creation;
- Source matching by Provider identity;
- Source metadata updates;
- Blob versioning for content changes;
- content-hash requirements;
- reuse of existing content;
- Source deactivation Decisions.

Identity V1 does not yet define:

- Source reactivation;
- semantic merging based on AI judgment;
- complete temporal Source-to-Blob transition history;
- conflict resolution between simultaneous Provider observations;
- relationship inference between Assets.

## Related Documents

- [04 - Provider Fact](04-provider-fact.md)
- [05 - Sync Engine](05-sync-engine.md)
- [07 - Decision](07-decision.md)
- [09 - World Model](09-world-model.md)
- [11 - Sync Lifecycle](11-sync-lifecycle.md)
