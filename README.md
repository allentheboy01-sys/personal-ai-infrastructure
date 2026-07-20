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

# Current Research

Current work focuses on building the foundations of PDI.

- Personal Digital Asset Model
- Metadata & Relationship Model
- Identity Representation
- Evidence-based Knowledge Organization
- Provider / Adapter Architecture
- Self-hosted Infrastructure
- Architecture Documentation

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

# Repository

| Document | Description |
| -------- | ----------- |
| Vision | Long-term goals and philosophy |
| Research | Research questions and ongoing exploration |
| Architecture | Overall system architecture |
| Data Model | Digital asset representation |
| Roadmap | Development milestones |
| Decisions | Architecture decision records |

---

# Current Status

PDI is still in its early stages.

Many ideas are incomplete.

Many assumptions will change.

That is expected.

This repository documents the evolution of the project as much as the project itself.

The current implementation has two real Providers:

- Nextcloud
- Immich

Both Providers use the same PDI Core flow:

```text
Provider
→ Adapter
→ ProviderFact
→ Matcher
→ Decision / Requirement
→ SyncEngine
→ PostgreSQLRepository
→ PostgreSQL
```

For Immich, `connect()`, `scan()`, original-content `open()`, SHA-256
verification, PostgreSQL persistence, and a second idempotent synchronization
have been validated against real services. The second synchronization preserves
the existing Source and Blob identities instead of creating duplicates.

Discussions, criticism, and alternative perspectives are always welcome.

---

> **I don't want to build an AI.**
>
> **I want to build the foundation that allows every future AI to truly understand people.**
