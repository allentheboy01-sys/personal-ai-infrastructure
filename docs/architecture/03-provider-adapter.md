# Provider Adapter

## Purpose

A Provider Adapter is the communication layer between PDI and an external application.

Every Provider is accessed through an Adapter.

---

## Responsibilities

An Adapter is responsible for:

- Connecting to a Provider.
- Reading provider-specific data.
- Converting data into ProviderFacts.
- Opening file streams when requested.

---

## Does NOT

An Adapter does NOT:

- Make identity decisions.
- Access the World Model.
- Store data.
- Execute synchronization logic.

---

## Notes

- Every Provider has its own Adapter.
- PDI never communicates with Providers directly.
- Provider-specific details are isolated inside Adapters.