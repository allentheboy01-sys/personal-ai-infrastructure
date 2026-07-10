# 01 - Overview

**Status:** V0.1

---

## Purpose

PDI (Personal Digital Infrastructure) builds a stable World Model for a person's digital life.

Applications, AI models and storage systems may change.

The World Model should remain stable.

---

## Data Flow

```
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

Each chapter in this document describes one step of the workflow above.

---

## AI Interaction

PDI is independent of any AI system.

AI does not communicate with Providers directly.

Instead, AI interacts with the World Model through PDI.

```
User
    │
    ▼
AI Interface
    │
    ▼
Repository
    │
    ▼
World Model
```

---

## Architecture Principles

- Providers remain independent.
- Adapters isolate Provider-specific implementations.
- ProviderFacts are temporary.
- Identity makes decisions.
- Decisions describe changes.
- Repositories execute changes.
- The World Model is Provider-independent.
- AI interacts with the World Model instead of individual Providers.

---

## Reading Order

The Architecture documents follow the same order as the data flow.

```
01 Overview
        ↓
02 Provider
        ↓
03 Provider Adapter
        ↓
04 Provider Fact
        ↓
05 Sync Engine
        ↓
06 Identity
        ↓
07 Decision
        ↓
08 Repository
        ↓
09 World Model
        ↓
10 Capability
```