# 03 - Provider Adapter

**Status:** Stable

## Purpose

A Provider Adapter is the anti-corruption boundary between PDI and one external Provider.

Every Provider is accessed through an Adapter. Provider-specific protocols, field names, authentication, pagination, and transport details remain inside this boundary.

## Responsibilities

An Adapter is responsible for:

- connecting to its Provider;
- scanning observable Provider objects;
- translating Provider data into `ProviderFact` objects;
- opening content streams when the Sync Engine requests them;
- preserving useful raw Provider metadata without exposing Provider-specific behavior to PDI Core.

## Contract

An Adapter must provide stable PDI-facing behavior even when the Provider API is different.

A scan emits observations. It does not create Assets, Blobs, Sources, Decisions, or database rows.

A single synchronization run must represent one Provider identity consistently.

## Does NOT

An Adapter does not:

- make identity decisions;
- query or mutate the World Model;
- calculate semantic relationships;
- execute repository operations;
- decide whether missing objects should be deactivated;
- contain synchronization-session policy.

## Content Access

Content should be opened only when required. Lightweight metadata such as external identifiers and version tags is preferred before expensive content reads or hashes.

## Related Documents

- [02 - Provider](02-provider.md)
- [04 - Provider Fact](04-provider-fact.md)
- [05 - Sync Engine](05-sync-engine.md)
