# PDI Documentation

This directory contains the current architecture specification and implementation context for PDI.

## Structure

```text
docs/
├── architecture/   Architecture specification and invariants
├── context/        Current implementation state
└── decisions/      Architecture Decision Records (ADR)
```

## Architecture

Read the architecture documents in this order:

1. [Architecture Overview](architecture/01-overview.md)
2. [Provider](architecture/02-provider.md)
3. [Provider Adapter](architecture/03-provider-adapter.md)
4. [Provider Fact](architecture/04-provider-fact.md)
5. [Sync Engine](architecture/05-sync-engine.md)
6. [Identity](architecture/06-identity.md)
7. [Decision](architecture/07-decision.md)
8. [Repository](architecture/08-repository.md)
9. [World Model](architecture/09-world-model.md)
10. [Capability](architecture/10-capability.md)
11. [Sync Lifecycle](architecture/11-sync-lifecycle.md)

## Context

[CURRENT_CONTEXT.md](context/CURRENT_CONTEXT.md) records the current implementation state, completed milestones, known boundaries, and immediate next work.

Context documents may change frequently. They are not permanent architecture specifications.

## Decisions

The `decisions/` directory is reserved for Architecture Decision Records.

An ADR should be added when PDI makes a significant design choice whose reasoning and consequences should remain understandable even after the implementation changes.

## Documentation Rules

1. Architecture documents describe current valid design, not historical discussion.
2. Context documents describe the present implementation state.
3. Git history records previous versions.
4. Code must implement the architecture specification.
5. A new abstraction must reduce total complexity.
6. Significant architecture changes must update the relevant documents before or with the implementation.
