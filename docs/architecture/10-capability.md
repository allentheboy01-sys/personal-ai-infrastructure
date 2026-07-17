# 10 - Capability

**Status:** Stable for Identity V1

## Purpose

A Capability is a reusable operation that produces evidence or transformation results without owning business meaning.

Capabilities allow PDI components to request expensive or specialized work without embedding that work inside Identity, Adapters, Repositories, or the Sync Engine.

## Responsibilities

A Capability is responsible for:

- performing one focused reusable operation;
- accepting explicit inputs;
- returning explicit results;
- remaining independent from World Model decisions;
- being callable only when the orchestration flow requires it.

## Current Capability

Identity V1 currently uses:

```text
SHA-256 content hashing
```

The Sync Engine opens content through the Adapter, passes the stream to the hashing Capability, enriches the `ProviderFact`, and invokes Identity again.

## Does NOT

A Capability does not:

- decide whether an Asset, Blob, or Source should exist;
- access Provider APIs unless the caller supplies the required input;
- query or mutate the World Model;
- persist results directly;
- execute Decisions;
- coordinate synchronization;
- become a hidden service layer containing unrelated business logic.

## Invocation Model

Capabilities are demand-driven.

```text
Identity
   │
   ▼
Requirement
   │
   ▼
Sync Engine
   │
   ▼
Capability
   │
   ▼
Enriched ProviderFact
```

The component requesting evidence does not need to know the implementation details of the Capability.

## Design Principles

1. A Capability should perform one coherent operation.
2. Capability output should be deterministic when the underlying operation is deterministic.
3. Business decisions remain in Identity.
4. Provider communication remains in Adapters.
5. Persistence remains in Repositories.
6. Orchestration remains in the Sync Engine.
7. A new Capability must reduce duplication or coupling.
8. Expensive Capabilities should be invoked only when cheaper evidence is insufficient.

## Possible Future Capabilities

Examples may include:

- metadata extraction;
- EXIF extraction;
- text extraction;
- OCR;
- audio transcription;
- thumbnail generation;
- embedding generation;
- media fingerprinting.

Listing a possible Capability does not make it part of the current architecture. Each addition requires a concrete consumer and a defined contract.

## Related Documents

- [03 - Provider Adapter](03-provider-adapter.md)
- [05 - Sync Engine](05-sync-engine.md)
- [06 - Identity](06-identity.md)
- [11 - Sync Lifecycle](11-sync-lifecycle.md)
