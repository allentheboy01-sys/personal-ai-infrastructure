# ADR-000: Architecture Decision Record Guidelines

- **Status:** Accepted
- **Date:** 2026-07-19
- **Scope:** Project-wide architecture governance

## Context

PDI is intended to evolve over a long period while remaining understandable and maintainable by one person. Architectural decisions must therefore be recorded separately from implementation details, temporary experiments, and conversational notes.

Without a clear ADR process, code changes may silently redefine the domain model, introduce incompatible abstractions, or make future contributors unable to distinguish deliberate design from incidental implementation.

## Decision

PDI uses Architecture Decision Records to document decisions that materially affect the structure, invariants, boundaries, or long-term evolution of the system.

An ADR records a decision. It is not a task list, implementation log, meeting transcript, or substitute for code documentation.

## When an ADR is required

Create an ADR when a proposed change affects one or more of the following:

- the PDI domain model or its invariants;
- ownership or lifecycle of persisted data;
- boundaries between Core, Adapter, Provider, Repository, Runtime, and Interface layers;
- public interfaces used across modules;
- persistence strategy or migration rules;
- security, privacy, or trust boundaries;
- a project-wide engineering rule that future work must follow;
- a deliberate rejection of a plausible architectural alternative.

An ADR is normally not required for:

- bug fixes that preserve existing architecture;
- local refactoring with no public or domain impact;
- test additions;
- formatting or documentation corrections;
- provider-specific implementation details that do not change Core contracts.

## File naming

ADR files use the following format:

```text
NNN-short-kebab-case-title.md
```

Examples:

```text
000-adr-guidelines.md
001-domain-model-v1.md
002-core-v0.2-migration-plan.md
```

Numbers are never reused, even if an ADR is later superseded.

## Required structure

Every ADR should include:

1. **Title and number**
2. **Status**
3. **Date**
4. **Scope**
5. **Context**
6. **Decision**
7. **Consequences**
8. **Rejected alternatives**, when meaningful
9. **Change or supersession policy**, when the decision is frozen or long-lived

Implementation-oriented ADRs may additionally include sequencing, validation, rollback, and compatibility constraints.

## Status values

Use one of the following statuses:

- **Proposed** — under review and not yet binding;
- **Accepted** — approved and binding;
- **Accepted and frozen** — approved, binding, and change-controlled;
- **Superseded by ADR-NNN** — replaced by a later decision;
- **Rejected** — considered but not adopted;
- **Deprecated** — still present for compatibility but no longer preferred.

Do not silently rewrite the meaning of an accepted ADR.

## Updating an ADR

Small clarifications that do not alter the decision may be added directly.

A change that alters meaning, invariants, ownership, lifecycle, or architectural boundaries requires one of the following:

- a new ADR that supersedes the previous ADR; or
- an explicit amendment section approved as part of an architecture review.

Frozen ADRs must not be changed merely because an implementation is inconvenient.

## Relationship to implementation

The required workflow for architecture-affecting changes is:

```text
Problem or validated use case
  -> ADR or existing ADR review
  -> impact analysis
  -> migration or implementation plan
  -> implementation
  -> tests and verification
  -> review
  -> merge
```

Code must implement accepted ADRs. Code must not redefine them implicitly.

When code and an accepted ADR conflict, the conflict must be surfaced explicitly. The implementation must not be changed casually, and the ADR must not be weakened to hide the mismatch.

## Relationship to Codex and other AI tools

AI coding tools may inspect, implement, test, and report changes. They do not have authority to decide or modify PDI architecture.

Before architecture-sensitive work, an AI tool must be given the relevant ADRs and explicit scope constraints.

If an AI tool discovers that the requested implementation conflicts with an accepted ADR, it must stop and report the conflict rather than inventing a new design.

## Consequences

### Positive

- Architectural intent remains visible outside the codebase.
- Future refactors can distinguish deliberate constraints from accidental structure.
- AI-assisted implementation remains subordinate to human-approved design.
- The project can evolve without repeatedly reopening settled decisions.

### Costs

- Architecture-affecting work requires written review before coding.
- Some implementation work may pause when a hidden design conflict is discovered.
- ADRs require maintenance when decisions are superseded.

## Change policy

This ADR governs the ADR process itself. Material changes to this process require a new ADR that supersedes ADR-000.