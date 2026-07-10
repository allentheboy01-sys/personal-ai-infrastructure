# Decision

## Purpose

A Decision is the output of the Identity Matcher.

It describes what changes should happen to the World Model.

A Decision never performs those changes itself.

---

## Why

Identity determines what should happen.

Repository performs the actual changes.

Separating these responsibilities keeps business logic independent from storage.

---

## Responsibilities

A Decision is responsible for:

- Describing required Actions.
- Reporting missing Requirements.
- Explaining the matching result.
- Providing a confidence score.

---

## Does NOT

A Decision does NOT:

- Modify the World Model.
- Access Providers.
- Read file contents.
- Execute database operations.

---

## Workflow

```text
ProviderFact
        │
        ▼
 Identity Matcher
        │
        ▼
     Decision
        │
        ▼
 Repository
```

The Sync Engine may first satisfy any Requirements before the Decision becomes executable.

---

## Notes

Current Requirements:

- Content Hash

Current Actions:

- Create Asset
- Create Blob
- Create Source
- Update Source

Future versions may introduce additional Requirement and Action types without changing the overall workflow.