# 01 - Overview

**Status:** V0.1 Draft

---

## Core Idea

PDI is a stable World Model for a person's digital life.

It does not replace Providers.

It does not replace AI.

It creates a unified semantic layer above all Providers.

---

## System Architecture

    User
      ↓
    Jarvis / AI Interface
      ↓
    PDI
      ↓
    World Model
    Asset / Blob / AssetSource
      ↓
    Repository
      ↓
    Identity Matcher
      ↓
    Sync Engine
      ↓
    ProviderFact
      ↓
    Adapter
      ↓
    Provider
    Nextcloud / Immich / Git / ...

---

## Layer Responsibilities

| Layer | Responsibility |
|---|---|
| User | Gives intent |
| AI Interface | Understands natural language |
| PDI | Owns the digital world model |
| World Model | Defines Asset, Blob, AssetSource |
| Repository | Persists and retrieves world objects |
| Identity Matcher | Decides whether ProviderFacts map to existing or new Assets |
| Sync Engine | Detects changes from Providers |
| ProviderFact | Temporary fact returned by Adapter |
| Adapter | Talks to Providers |
| Provider | Owns original application data |

---

## Core Rule

Every layer removes implementation details from the layer below.

Examples:

- Adapter hides Provider API differences.
- Sync Engine hides scanning and diff details.
- Identity Matcher hides identity uncertainty.
- Repository hides database implementation.
- World Model hides all Provider-specific structure.
- AI only sees a unified digital world.