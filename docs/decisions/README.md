# Architecture Decision Records

This directory stores Architecture Decision Records (ADRs) for significant PDI design choices.

Architecture documents explain the current valid design. ADRs explain why an important choice was made, which alternatives were considered, and what consequences follow from that choice.

## When to Add an ADR

Add an ADR when a decision:

- changes a core architectural boundary;
- introduces or removes a major abstraction;
- establishes a long-lived invariant;
- chooses between meaningful alternatives;
- creates consequences that future contributors must understand.

Routine implementation details do not require ADRs.

## Naming

Use sequential names:

```text
0001-short-decision-title.md
0002-another-decision.md
```

## Template

```markdown
# ADR-XXXX: Decision Title

**Status:** Proposed | Accepted | Superseded

## Context

What problem or pressure requires a decision?

## Decision

What has been decided?

## Rationale

Why was this option selected?

## Alternatives Considered

What other options were evaluated?

## Consequences

What becomes easier, harder, required, or prohibited?

## Related Documents

Which architecture or context documents are affected?
```

## Rule

ADRs preserve reasoning. They must not duplicate complete component specifications or become a changelog.
