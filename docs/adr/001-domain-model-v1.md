# ADR-001: PDI Domain Model V1

- **Status:** Accepted and frozen
- **Date:** 2026-07-19
- **Scope:** PDI Core domain model

## Context

PDI is not a mirror of any single provider. Providers, applications, AI systems, databases, and interfaces may be replaced, while PDI must preserve a stable representation of a person's digital life.

PDI Core therefore needs a small domain model whose concepts remain stable across providers and implementation changes.

This ADR freezes the first version of that model. Future code must adapt to this model. The model must not be changed merely to make an implementation easier.

## Decision

PDI Core V1 has five domain entities:

- `Asset`
- `Blob`
- `Source`
- `Relation`
- `Tag`

Runtime concepts such as `ProviderFact`, `Decision`, `Action`, and `Requirement` are not domain entities.

---

## 1. Asset

### Definition

An `Asset` is an independently managed digital object in PDI with its own digital lifecycle.

Examples may include files, photos, contacts, events, and projects. An Asset is not created merely because a real-world concept exists. It exists only when PDI has an independently managed digital state for it.

### Creation

An Asset must originate from a Blob.

```text
Provider
  -> ProviderFact
  -> Blob candidate
  -> Identity matching
  -> existing Asset or new Asset
```

PDI must not create an empty Asset that has no Blob-backed digital state.

### Lifecycle

An Asset is created once and is never physically deleted by provider synchronization.

```text
ACTIVE -> INACTIVE
```

The disappearance of one or all Sources does not automatically make an Asset inactive. Inactivation is an explicit PDI or user decision.

### Type

`AssetType` is a fixed enum maintained by PDI Core.

A provider may map its objects to existing Asset types, but it may not define arbitrary new types. When a genuinely new kind of independently managed digital object is introduced, the type enum may be extended deliberately as part of a domain-model review.

The current implementation only needs the file/document type. Future types are added only when a provider and its use cases require them.

### Presentation metadata

An Asset may keep stable presentation fields such as `title` or `display_name` so common listings do not require loading a Blob merely to display the object.

Presentation metadata is not a separate domain entity.

---

## 2. Blob

### Definition

A `Blob` is the complete digital state of an Asset at a particular point in time.

A Blob is immutable. A change in state creates a new Blob instead of mutating an existing one.

### State model

Blob uses a hybrid state model:

- frequently queried common fields remain strongly typed, such as content hash, size, and MIME type;
- type-specific state is stored in a structured `state` field, implemented as JSONB in PostgreSQL.

Examples of type-specific state include contact fields, event times, or message metadata.

### Lifecycle

Blobs preserve history. They are not active or inactive and do not follow provider lifecycle directly.

A Blob may remain in PDI even after its original Source is no longer active.

### Identity

A Blob is identified by its own internal `blob.id`.

A content hash is a fingerprint used for matching and integrity checks. It is not the identity of the Blob.

---

## 3. Source

### Definition

A `Source` records where a Blob came from in an external provider.

Typical fields include:

- provider identifier;
- external object identifier;
- path or provider location;
- ETag or provider version marker;
- provider-specific source metadata.

### Ownership

A Source belongs to a Blob, not directly to an Asset.

Multiple Sources may refer to the same Blob when identical state is available from multiple providers or locations.

### Boundary

Source stores provider-origin metadata. It must not become a second place for domain business state that belongs in Blob state.

A provider may create, update, deactivate, or remove its Source representation, but it cannot delete the corresponding Asset or erase Blob history.

---

## 4. Relation

### Definition

A `Relation` connects one Asset to another Asset for organization, navigation, and retrieval.

Relation is PDI's navigation graph. It is not intended to model every fact about the real world and is not a general-purpose knowledge graph.

Examples of facts that are outside the core Relation model include friendship, parenthood, employment, or other open-ended real-world semantics. Such information may exist in Blob state belonging to a relevant Asset type.

### Endpoints

Both endpoints of a Relation must be Assets.

Relations never connect directly to Blobs, Sources, or Tags.

### Direction

Every Relation type defines the meaning of its direction.

For a hierarchical relation such as `PART_OF`, storage follows:

```text
child Asset -> PART_OF -> parent Asset
```

Storage direction does not restrict query direction. PDI may query child-to-parent or parent-to-children.

Assets that appear to be peers do not require pairwise peer relations. They may be derived as siblings because they share the same parent Asset, or grouped through a shared Tag.

### Cycles

Relations must not create cycles. At minimum, hierarchical relations such as `PART_OF` must form a directed acyclic graph.

### Lifecycle

Relations describe current navigation structure. They are mutable, removable, and rebuildable. Relation history and relation versioning are outside V1.

### Relation types

The exact Relation type catalog is intentionally not expanded in this ADR beyond the minimum required by an implemented use case. New Relation types must remain few, directional, and navigation-oriented.

---

## 5. Tag

### Definition

A `Tag` is a reusable concept used to describe and retrieve Assets.

A Tag does not require a Blob and does not need to correspond to another Asset.

This allows PDI to describe concepts that are useful for search but do not have an independently managed digital state, such as a recognized landmark, topic, person name, place, or visual concept.

### Data model

Tag is an independent entity with a stable internal identity.

```text
Tag
- id
- name

AssetTag
- asset_id
- tag_id
```

Using a Tag entity instead of storing repeated strings allows later normalization, aliases, merging, statistics, and consistent references without rewriting every Asset association.

### Production boundary

PDI Core V1 stores and associates Tags but does not define an AI-driven automatic tagging pipeline.

Tags may be supplied by a provider or explicitly by a user. Future AI systems may propose Tags, but proposal, filtering, confidence policy, and automatic creation are deferred.

---

## 6. Identity matching

Identity matching decides which Asset a Blob belongs to.

Matching is dispatched by `AssetType`. Each supported type has its own matcher, for example:

```text
FILE -> FileMatcher
CONTACT -> ContactMatcher
EVENT -> EventMatcher
```

Adding an Asset type requires adding its matcher rather than expanding one universal matcher with type-specific conditionals.

The current implementation only requires the existing file matcher.

---

## Invariants

PDI Core V1 must preserve the following invariants:

1. Every Asset is created from at least one Blob-backed digital state.
2. Every Blob belongs to exactly one Asset.
3. Blob records are immutable.
4. Source belongs to Blob, not directly to Asset.
5. Provider lifecycle cannot physically delete an Asset or Blob history.
6. Relation endpoints are always Assets.
7. Stored Relations are directional and may be queried in either direction.
8. Relations must not create cycles.
9. Tag is not an Asset and requires no Blob.
10. Asset type and Relation type vocabularies are controlled by PDI Core, not by individual providers.
11. Identity matching is type-specific.

---

## Explicitly deferred from V1

The following are outside this decision and must not be introduced during the V0.2 domain-model refactor unless separately approved:

- AI-generated Tag pipeline;
- open-ended knowledge graph predicates;
- storage of arbitrary real-world facts as core Relations;
- Relation history or versioning;
- provider-defined or dynamic Asset types;
- a large predesigned Relation type catalog;
- new providers or user-facing features unrelated to the refactor.

---

## Consequences

### Positive

- PDI remains independent of provider lifecycle.
- Digital history is preserved through immutable Blobs.
- Provider metadata is isolated in Source.
- Navigation structure and descriptive concepts remain separate.
- New Asset types can add focused matchers without destabilizing existing matching logic.
- The model remains small enough for one person to maintain.

### Costs

- Blob history requires explicit current-state selection.
- Tag associations require normalized tables and repository operations.
- Relation validation must prevent cycles.
- Adding an Asset type requires deliberate model review and a dedicated matcher.

## Change policy

This ADR is frozen for PDI Domain Model V1.

It may be amended only when a concrete provider or validated use case cannot be represented by the existing model. Implementation inconvenience alone is not sufficient justification.
