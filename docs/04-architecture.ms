
# Architecture

PDI is not an AI assistant.

PDI is not a large language model.

PDI is not a replacement for existing applications.

PDI is the infrastructure between people, AI systems, and personal digital assets.

Its responsibility is to organize, represent, and provide access to a person's digital life in a way that remains independent of any individual AI system.

---

# Design Philosophy

The architecture of PDI is guided by one principle.

> Every component should answer a research question.

Technology choices are expected to change.

The architecture should remain stable.

---

# High-level Architecture

```text
                    User
                      │
                      ▼
              AI Interface / Agent
                      │
                      ▼
                     PDI
     ┌────────────────┼────────────────┐
     │                │                │
     ▼                ▼                ▼
 Data Model      Retrieval       Rule Engine
     │                │                │
     └────────────────┼────────────────┘
                      │
                      ▼
             Provider / Adapter Layer
                      │
     ┌────────────┬────────────┬────────────┐
     ▼            ▼            ▼
 Nextcloud     Immich      Email / Calendar
     ▼            ▼            ▼
            Other Data Sources
```

---

# Responsibilities

## AI Interface

Provides interaction between people and AI.

Examples include ChatGPT, Claude, Gemini, Codex, or future AI systems.

PDI does not depend on any single interface.

---

## PDI Core

The core of the system.

Responsible for:

- Organizing personal digital assets
- Maintaining metadata
- Managing relationships
- Identity representation
- Knowledge retrieval
- Evidence management

The core should never depend on a specific AI model.

---

## Provider / Adapter Layer

Applications already solve domain-specific problems.

Examples include:

- Nextcloud
- Immich
- Email
- Calendar
- Git
- Obsidian

PDI does not replace these applications.

Instead, adapters translate their data into a unified representation.

---

# Design Principles

The architecture follows several long-term principles.

- AI systems are replaceable.
- Providers remain independent.
- Data should have a single unified representation.
- Every layer has a single responsibility.
- Research questions drive architectural decisions.

---

# Current Status

The architecture is still evolving.

Many components are placeholders for ongoing research.

The purpose of this document is to explain the current direction rather than define a final implementation.
