# 02 - Provider

**Status:** Stable

## Purpose

A Provider is an external system that owns and manages original user data within its own domain.

Examples include Nextcloud, Immich, email systems, Git repositories, Home Assistant, and messaging platforms.

## Responsibilities

A Provider is responsible for:

- creating or receiving original data;
- enforcing its own permissions and domain rules;
- maintaining Provider-specific identifiers and metadata;
- exposing supported interfaces for reading or operating on its data.

## Authority Boundary

A Provider is authoritative about its current observable state, but it is not authoritative about PDI semantic identity.

For example, a Provider can state that an object exists, moved, changed version, or disappeared. It cannot decide whether that object is a new Asset, a new Blob, or another Source of existing content.

## Does NOT

A Provider does not:

- understand the PDI World Model;
- create or mutate PDI entities directly;
- make identity decisions;
- coordinate synchronization;
- communicate with other Providers through PDI internals.

## Independence

PDI does not copy a Provider's architecture or depend on its internal database schema. Integration occurs only through a Provider Adapter and supported Provider interfaces.

Replacing one Provider must not require redesigning the World Model.

## Related Documents

- [03 - Provider Adapter](03-provider-adapter.md)
- [04 - Provider Fact](04-provider-fact.md)
- [09 - World Model](09-world-model.md)
