# Provider Fact

## Purpose

A ProviderFact is the unified representation of data produced by a Provider Adapter.

It is the only format accepted by the Sync Engine.

---

## Responsibilities

A ProviderFact carries:

- Provider identity.
- External identifier.
- Provider metadata.
- Available attributes.

---

## Does NOT

A ProviderFact does NOT:

- Exist in the World Model.
- Represent an Asset.
- Store semantic relationships.
- Persist in the database.

---

## Notes

- ProviderFacts are temporary.
- They exist only during synchronization.
- After synchronization, only World Model entities remain.