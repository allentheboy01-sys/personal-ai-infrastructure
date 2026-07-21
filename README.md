# Personal Digital Infrastructure (PDI)

> **AI systems come and go. People don't.**

Personal Digital Infrastructure (PDI) is a long-term, research-driven open project exploring one fundamental question:

> **How can a person's digital life remain continuous while AI systems continue to change?**

I believe AI will become one of the most important technologies of this century.

But AI can only truly help people if it truly understands the people it serves.

Today, every AI system builds its own memory.

When people change AI products, they often start over.

The memory belongs to the product—not to the person.

PDI explores an alternative.

Instead of building another AI assistant, it explores the infrastructure that allows every future AI system to understand the same person through a digital life that belongs to the individual.

---

# Why

I started this project because I wanted to build an AI that could genuinely understand me.

While exploring existing AI systems, I realized that the real problem was not intelligence.

The real problem was ownership.

Every AI remembers people differently.

Every platform stores a different version of the same person.

There is no persistent digital foundation that truly belongs to the individual.

That realization completely changed the direction of this project.

Instead of asking,

> **"How can we build a better AI?"**

I began asking,

> **"What should exist before AI?"**

PDI is my current answer to that question.

---

# Research Questions

PDI currently explores several long-term research questions.

### Reality → Digital Life

How can real-world experiences become meaningful digital representations?

### Digital Representation

How should a person's digital life be represented over decades rather than conversations?

### Shared Understanding

How can different AI systems understand the same person without owning that person's memory?

### Ownership

How can people remain the long-term owners of their digital lives regardless of which applications or AI systems they use?

---

# Current Implementation

PDI Core v0.2.0 currently includes:

- Provider / Adapter architecture;
- normalized `ProviderFact` observations;
- Identity V1 matching and lifecycle decisions;
- `Asset`, `Blob`, and `AssetSource` World Model entities;
- PostgreSQL persistence through a Repository boundary;
- Nextcloud and Immich Provider integrations;
- SHA-256 content verification on demand;
- migration, repository, adapter, and real-service integration tests;
- incremental and idempotent synchronization validated against real services.

Both real Providers use the same stable PDI Core pipeline:

```text
Provider
→ Adapter
→ ProviderFact
→ SyncEngine
   ├── Identity / Matcher
   ├── Requirement → Adapter / Capability
   └── Decision → Repository
                         ↓
                 PostgreSQL World Model
```

# Future Research

Current and future research directions include:

- metadata and relationship models;
- evidence-based knowledge organization;
- semantic retrieval over personal digital assets;
- long-term digital identity and history;
- AI interfaces that consume PDI without defining it.

The implementation evolves together with the research.

Every architectural decision begins with a research question rather than a technology choice.

---

# Design Principles

Several principles guide every design decision in this project.

- AI is replaceable.
- Personal data is persistent.
- Infrastructure should outlive individual technologies.
- Digital memory belongs to people, not AI products.
- Engineering should serve research, not the other way around.
- Every assumption is open to discussion.

---

# Documentation

| Document | Description |
| -------- | ----------- |
| [Documentation Index](docs/README.md) | Reading order and documentation rules |
| [Architecture Overview](docs/architecture/01-overview.md) | Current architecture and invariants |
| [Current Context](docs/context/CURRENT_CONTEXT.md) | Current implementation status and immediate next work |
| [Architecture Decisions](docs/decisions/README.md) | ADR guidance and decision records |
| [Roadmap](ROADMAP.md) | Development milestones |

---

# Current Status

PDI remains an early-stage project, but the core ingestion foundation is now real and tested.

The current implementation has two real Providers:

- Nextcloud
- Immich

For Immich, `connect()`, `scan()`, original-content `open()`, SHA-256 verification, PostgreSQL persistence, incremental synchronization, and idempotent synchronization have been validated against real services.

PDI Core v0.2.0 also includes protected `_test` database integration workflows, automatic Alembic migration of empty test databases, and regression coverage that prevents Alembic logging setup from disabling existing PDI loggers.

Discussions, criticism, and alternative perspectives are always welcome.

---

> **I don't want to build an AI.**
>
> **I want to build the foundation that allows every future AI to truly understand people.**
