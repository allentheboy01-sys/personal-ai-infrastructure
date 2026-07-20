# Roadmap

PDI is a long-term research project.

This roadmap describes the expected evolution of the project.

It is intended to guide development rather than predict the future.

---

# Phase 1 — Foundation

Current Stage

Focus:

- Research vision
- Research questions
- Repository organization
- High-level architecture
- Self-hosted infrastructure
- Documentation

Status:

🟢 In Progress

---

# Phase 2 — Data Foundation

Focus:

- Digital asset model
- Metadata model
- Relationship model
- Identity representation
- Evidence model

Goal:

Establish a unified representation of personal digital life.

---

# Phase 3 — Infrastructure

Focus:

- Provider / Adapter framework
- PostgreSQL integration
- Nextcloud integration
- Immich integration
- Local storage
- Synchronization

Goal:

Connect existing digital services into one unified infrastructure.

Current implementation:

- Nextcloud and Immich both enter the same ProviderFact-based PDI Core;
- both Providers use the shared Matcher, SyncEngine, Repository, and World Model;
- Immich connect, scan, original download, SHA-256 verification, PostgreSQL
  persistence, and idempotent repeat synchronization have been validated.

---

# Phase 4 — Knowledge Layer

Focus:

- Knowledge graph
- Retrieval
- Context construction
- Long-term memory
- Semantic relationships

Goal:

Allow AI systems to understand a person's digital life instead of isolated files.

---

# Phase 5 — AI Integration

Focus:

- AI interface
- Agent integration
- Context sharing
- Task execution
- Decision support

Goal:

Enable different AI systems to share the same understanding of a person.

---

# Phase 6 — Open Research

Future work may include:

- Reality → Digital Life
- Automatic knowledge organization
- Human digital representation
- Personal digital identity
- Long-term digital evolution

The exact direction will evolve as new research questions emerge.

---

# Guiding Principle

PDI is expected to change.

The roadmap is not a fixed plan.

It is a record of how the project evolves through continuous research and engineering.
