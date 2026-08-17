# PDI Documentation

This directory contains PDI's current architecture, implementation context,
deployment procedures, development workflow, frozen designs, release notes,
roadmap, and decision records.

## Structure

```text
docs/
├── architecture/   Architecture specifications and invariants
├── context/        Current implementation state
├── deployment/     Validated production/runtime procedures
├── development/    Contributor and Codex workflows
├── design/         Frozen capability designs and validation records
├── releases/       Release notes
├── roadmap/        Delivery order
└── adr/            Architecture Decision Records
```

## Architecture

Start with the current system map in [`../ARCHITECTURE.md`](../ARCHITECTURE.md).
The original Core specifications remain in `architecture/`:

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

## Current context

[`context/CURRENT_CONTEXT.md`](context/CURRENT_CONTEXT.md) records the current
implementation, completed capabilities, validation state, boundaries, and next
work. It may change frequently and is not a permanent architecture history.

## Development and deployment

- [Codex CLI on pdi-server](development/codex-cli-on-pdi-server.md)
- [PDI server runtime](deployment/server-runtime-v0.1.md)
- [Jarvis runtime](deployment/jarvis-runtime-server-v0.1.md)

## Releases

- [v0.5.0 — Personal Retrieval Runtime](releases/v0.5.md)
- [v0.4.0 — Jarvis Tool Execution MVP](releases/v0.4.md)

## Decisions

The `adr/` directory contains Architecture Decision Records. Add an ADR when a
significant design choice and its consequences must remain understandable after
the implementation changes.

## Documentation rules

1. Architecture documents describe current valid design, not historical discussion.
2. Context documents describe the present implementation state.
3. Release notes and Git history record delivered history.
4. Code must implement the architecture specification.
5. A new abstraction must reduce total complexity.
6. Significant contract changes update their documentation in the same change.
