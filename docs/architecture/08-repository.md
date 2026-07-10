# Repository

## Purpose

The Repository is the access layer of the World Model.

It stores, retrieves and updates domain objects while hiding the underlying storage implementation.

---

## Why

Identity should not know how data is stored.

Whether the storage is in memory or PostgreSQL should not affect business logic.

The Repository isolates storage from the rest of the system.

---

## Responsibilities

A Repository is responsible for:

- Querying the World Model.
- Executing Decisions.
- Persisting domain objects.
- Providing a stable interface to storage.

---

## Does NOT

A Repository does NOT:

- Communicate with Providers.
- Perform identity matching.
- Calculate hashes.
- Coordinate synchronization.

---

## Workflow

```text
Decision
      │
      ▼
 Repository
      │
      ▼
 World Model
```

The Repository translates Decisions into persistent changes.

The storage implementation is hidden from the caller.

---

## Notes

Current implementation:

- InMemoryRepository

Planned implementation:

- PostgreSQLRepository

Replacing the storage implementation should not require changes to the Identity Matcher or Sync Engine.