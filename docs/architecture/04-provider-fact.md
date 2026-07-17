# 04 - Provider Fact

**Status:** Stable for Identity V1

## Purpose

A `ProviderFact` is a normalized observation of one object in Provider reality.

It is the boundary object passed from a Provider Adapter into PDI Core. It allows Identity and the Sync Engine to operate without understanding Provider-specific APIs or schemas.

## Required Meaning

A ProviderFact may carry:

- Provider identity;
- stable external identifier;
- object kind;
- name and path;
- Provider version tag;
- size and MIME type;
- normalized attributes;
- preserved raw metadata;
- content hash, when a Requirement has been satisfied.

Not every field must be known during the first match attempt. Missing expensive information may be requested through a `Requirement`.

## Invariants

1. A ProviderFact describes Provider reality, not PDI identity.
2. It must not reference an `Asset`, `Blob`, or `AssetSource` as its own identity.
3. `provider + external_id` identifies the observed Provider object when the Provider offers a stable identifier.
4. Path and name are observable properties, not stable identity.
5. A content hash describes bytes; a version tag describes the Provider's view of change. They are not interchangeable.

## Lifetime

ProviderFacts are temporary synchronization inputs. They are not persisted as World Model entities and do not become database rows directly.

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

## Does NOT

A ProviderFact does not:

- decide whether an Asset already exists;
- represent a persistent Source;
- execute changes;
- express semantic relationships;
- prove that content changed when no content hash is available.

## Related Documents

- [03 - Provider Adapter](03-provider-adapter.md)
- [06 - Identity](06-identity.md)
- [07 - Decision](07-decision.md)
