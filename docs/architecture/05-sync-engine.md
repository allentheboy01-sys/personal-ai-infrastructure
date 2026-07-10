# 05 - Sync Engine

**Status:** V0.1

---

## Purpose

The Sync Engine coordinates one synchronization cycle between a Provider and the World Model.

It connects existing modules without making identity or storage decisions.

---

## Responsibilities

The Sync Engine is responsible for:

- Connecting to an Adapter.
- Receiving ProviderFacts.
- Sending facts to the Identity Matcher.
- Reading Decision requirements.
- Invoking Capabilities when required.
- Sending executable Decisions to the Repository.

---

## Does NOT

The Sync Engine does NOT:

- Make identity decisions.
- Interpret Provider-specific data.
- Define World Model entities.
- Store data directly.
- Schedule continuous synchronization.

---

## Workflow

```text
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
    ├── Requirement
    │       │
    │       ▼
    │   Capability
    │       │
    └───────┘
    │
    ▼
Decision
    │
    ▼
Repository
```

---

## Notes

Current implementation:

- `sync_once()`

Future versions may introduce:

- Continuous synchronization
- Background scheduling
- Retry mechanisms
- Parallel synchronization