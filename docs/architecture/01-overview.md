# 01 - Architecture Overview

**Status:** Stable for Identity V1

## Purpose

PDI (Personal Digital Infrastructure) maintains a stable, provider-independent World Model for a person's digital life.

Providers, storage engines, applications, AI models, agents, and interfaces may change. The World Model and the rules that protect its identity must remain stable.

PDI remains useful without AI. Jarvis is the first AI Interface built on top of PDI, not the project itself.

## System Boundary

```text
User
  │
  ▼
AI Interface / Application
  │
  ▼
PDI Core
  │
  ▼
Provider Adapter
  │
  ▼
Provider
```

PDI Core does not replace Providers. Nextcloud, Immich, email, Git, Home Assistant, and other systems continue to manage their own domain-specific data and behavior.

## Ingestion Architecture

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
Sync Engine
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

Each boundary has one responsibility:

- **Provider** owns Provider reality.
- **Adapter** translates Provider-specific representations.
- **ProviderFact** carries a normalized observation.
- **Sync Engine** owns the synchronization-session lifecycle.
- **Identity** determines how the World Model should change.
- **Decision** represents required actions or missing requirements.
- **Repository** queries and persists the World Model.
- **World Model** preserves stable digital identity and history.

## Core Principles

1. Providers are replaceable; the World Model is not.
2. AI consumes the World Model; AI does not define it.
3. Provider-specific concepts must not leak beyond the Adapter boundary.
4. ProviderFacts are observations, not persistent World Model entities.
5. Identity produces Decisions and never performs persistence.
6. Repositories execute Decisions but do not invent business meaning.
7. Content changes create new Blobs; existing Blobs are not mutated.
8. Missing Provider objects are deactivated only after a successful complete scan.
9. Every new abstraction must reduce overall complexity.
10. Architecture precedes implementation.

## Documentation Model

- `architecture/` describes what PDI is and the invariants implementations must preserve.
- `context/` describes the current implementation state.
- Git history records how the architecture evolved.

## Reading Order

1. Provider
2. Provider Adapter
3. Provider Fact
4. Sync Engine
5. Identity
6. Decision
7. Repository
8. World Model
9. Capability
10. Sync Lifecycle

## Related Documents

- [02 - Provider](02-provider.md)
- [09 - World Model](09-world-model.md)
- [11 - Sync Lifecycle](11-sync-lifecycle.md)
