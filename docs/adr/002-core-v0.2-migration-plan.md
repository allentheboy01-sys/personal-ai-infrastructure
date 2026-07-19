# ADR-002: PDI Core V0.2 Migration Plan

- **Status:** Accepted
- **Date:** 2026-07-19
- **Scope:** Migration from the current V0.1 implementation to the Domain Model V1 defined by ADR-001

## Context

PDI Core V0.1 has already achieved a real end-to-end synchronization loop:

```text
Nextcloud
  -> Adapter
  -> ProviderFact
  -> Identity / Matcher
  -> Decision (Actions and Requirements)
  -> SyncEngine
  -> PostgreSQLRepository
  -> PostgreSQL
```

That working loop must be preserved.

ADR-001 freezes a clearer Domain Model V1 consisting of:

- `Asset`
- `Blob`
- `Source`
- `Relation`
- `Tag`

V0.2 is therefore a controlled domain-model refactor. It is not a feature release and must not become a rewrite.

## Decision

The migration will be implemented incrementally. Each step must be independently reviewable, testable, and reversible.

No implementation step may begin until Codex or another implementation agent has completed a read-only impact analysis of the current repository and confirmed the exact affected files, public interfaces, tests, and database objects.

The impact analysis may refine file paths and sequencing, but it may not change the architectural decisions in ADR-001 or the migration boundaries in this ADR.

## Migration goals

V0.2 must:

1. preserve the existing Nextcloud synchronization loop;
2. align persisted entities and domain classes with ADR-001;
3. introduce only the minimum infrastructure required by the frozen model;
4. keep existing stable module boundaries unless a documented incompatibility requires a narrow change;
5. maintain or improve test coverage;
6. avoid unrelated provider, UI, AI, or automation work.

## Non-goals

V0.2 does not include:

- a second provider;
- AI-generated Tags;
- automatic Relation inference;
- a knowledge graph;
- a broad Relation type catalog;
- user-facing search or navigation interfaces;
- removal of Blob history;
- replacement of the existing Decision or SyncEngine architecture;
- a general rewrite of repository or adapter code.

## Step 0: Read-only impact analysis

Before modifying code, inspect the repository and report:

- the current domain dataclasses or models;
- SQLAlchemy ORM models and table names;
- repository interfaces and implementations;
- Decision, Action, and Requirement types;
- Identity and Matcher dependencies;
- SyncEngine flow and transaction boundaries;
- tests covering matching, repository persistence, and integration behavior;
- all references to `AssetSource`;
- all assumptions that Source currently belongs directly to Asset;
- all fields currently mixed between Blob state and provider-origin metadata;
- the exact command set required to run unit and integration tests.

The output must classify each finding as:

```text
must change
may change
must not change
unknown / requires review
```

No code changes are permitted in Step 0.

## Step 1: Introduce controlled AssetType

### Goal

Add a fixed `AssetType` enum to PDI Core and attach it to `Asset`.

The initial enum must contain only the type required by the current implementation. Use the existing project terminology after impact analysis confirms whether the canonical name is `FILE` or `DOCUMENT`. Do not add speculative future types merely because ADR-001 mentions possible examples.

### Constraints

- Provider code may map to the enum but may not define arbitrary type strings.
- Existing Assets must receive the current file/document type through a safe migration or explicit default.
- No new matcher behavior is introduced in this step.
- Public constructors should remain compatible where practical; any necessary signature change must be reported before implementation.

### Validation

- existing matcher tests pass;
- existing repository integration tests pass;
- new tests verify AssetType persistence and invalid-type rejection.

### Rollback

Remove the enum field and reverse its database migration without altering existing Asset identity.

## Step 2: Establish type-specific matcher dispatch

### Goal

Convert identity matching into an explicit dispatcher keyed by `AssetType`, while preserving the current file/document matching behavior unchanged.

Target structure:

```text
AssetType
  -> matcher implementation
```

The existing matcher logic should become or remain the dedicated matcher for the current type. V0.2 must not add Contact, Event, Message, Photo, or Project matchers.

### Constraints

- no large universal matcher with type-specific conditionals;
- no provider-specific matching rules inside the dispatcher;
- the existing matching decisions, confidence behavior, reasons, and requirements must remain compatible;
- the dispatcher must fail clearly when no matcher is registered for a type.

### Validation

- all existing matcher tests remain behaviorally equivalent;
- new tests verify correct dispatch and unsupported-type failure;
- SyncEngine still completes the existing Nextcloud loop.

### Rollback

Restore direct use of the current matcher without changing persisted data.

## Step 3: Introduce Blob state JSONB

### Goal

Add a structured `state` field to Blob using PostgreSQL JSONB while retaining strongly typed common fields such as hash, size, and MIME type.

For the current file/document type, `state` should initially default to an empty object unless impact analysis identifies existing type-specific state that clearly belongs there.

### Constraints

- do not move fields merely for aesthetic purity;
- content hash, size, and MIME type remain strongly typed;
- existing Blob rows must migrate safely with `{}` as state;
- Blob immutability must be preserved;
- no Contact, Event, or Message schema is designed in V0.2.

### Validation

- repository tests verify JSONB round trips;
- existing Blob creation remains compatible;
- historical Blob rows remain readable;
- synchronization produces the same matching result as before.

### Rollback

Drop the new state column after confirming no V0.2-only data has been written to it.

## Step 4: Rename and realign AssetSource as Source

### Goal

Align the current `AssetSource` concept with ADR-001 by introducing the canonical `Source` name and making Source belong to Blob.

This is the highest-risk migration step and must not be implemented until impact analysis identifies every current dependency and the existing database constraints.

### Target semantics

```text
Source
- id
- blob_id
- provider
- external_id
- path or provider location
- provider version marker such as ETag
- provider-specific source metadata
```

### Constraints

- do not destroy existing provider provenance;
- do not delete or recreate Assets merely to move a foreign key;
- do not move domain state into Source;
- preserve the existing end-to-end synchronization loop;
- if a compatibility alias or transitional adapter is safer than an atomic rename, use a staged migration;
- database migration and Python rename may be separated into substeps after impact analysis;
- avoid a repository-wide mechanical rename until semantic ownership is correct.

### Recommended staged implementation

1. add or confirm `blob_id` ownership and backfill it from existing associations;
2. update ORM relationships and repository writes;
3. update Decision and Action payloads only where required;
4. update SyncEngine integration points only where required;
5. introduce the canonical `Source` class and compatibility alias if needed;
6. remove obsolete direct Asset ownership only after tests prove the new path;
7. rename the database table only if the benefit exceeds migration risk.

The physical table may temporarily retain its old name if renaming it creates unnecessary risk. Domain semantics take priority over cosmetic database naming.

### Validation

- every Source belongs to exactly one Blob;
- existing provider metadata is preserved;
- repeated synchronization remains idempotent;
- zero-action synchronization still produces zero writes;
- integration tests verify Asset, Blob, and Source persistence order and foreign keys;
- no existing Asset is deleted or recreated.

### Rollback

Retain a reversible migration path and compatibility code until the new ownership model passes full integration tests.

## Step 5: Add Asset active state only if missing

### Goal

Confirm that Asset supports explicit active/inactive state consistent with ADR-001.

If the current implementation already has the accepted field and semantics, this step becomes verification only and no code change should be made.

### Constraints

- provider synchronization must never automatically inactivate an Asset solely because Sources disappear;
- no physical Asset deletion path is added;
- Blob receives no active/inactive field.

### Validation

- tests prove Source removal does not automatically inactivate Asset;
- tests prove Blob has no active/inactive lifecycle behavior;
- existing active Assets remain active after migration.

## Step 6: Add minimal Tag persistence

### Goal

Add storage capability for reusable Tags without adding an automatic production pipeline.

Minimum model:

```text
Tag
- id
- name

AssetTag
- asset_id
- tag_id
```

### Constraints

- Tag is not an Asset;
- Tag has no Blob, Source, or version history;
- name uniqueness and normalization rules must be deliberately minimal;
- V0.2 may use exact canonical-name uniqueness but must not invent alias, embedding, confidence, or merge systems;
- PDI Core stores and associates Tags but does not decide which Tags AI should generate;
- no automatic provider-to-Tag import is required unless the existing provider already exposes a validated tag field and the mapping is separately approved.

### Repository capabilities

The minimum repository behavior is:

```text
find Tag by canonical name
create Tag if explicitly requested
attach Tag to Asset
remove Tag from Asset
list Tags for Asset
```

The implementation may use idempotent get-or-create semantics inside a transaction, but AI or provider adapters must not directly write database rows.

### Validation

- duplicate AssetTag associations are prevented;
- repeated explicit creation of the same canonical Tag is idempotent;
- Tag removal does not affect Asset lifecycle;
- no automatic tagging code is introduced.

### Rollback

Drop Tag and AssetTag tables because no existing synchronization path depends on them.

## Step 7: Add minimal Relation persistence

### Goal

Add the storage foundation for navigation Relations without implementing automatic Relation production.

Minimum model:

```text
Relation
- id
- from_asset_id
- to_asset_id
- relation_type
```

V0.2 must support only the minimum Relation type required by an approved use case. If no current execution path requires Relations, the table and repository contract may be added without integrating them into SyncEngine.

### Constraints

- both endpoints must be Assets;
- self-relations are rejected;
- hierarchical relations such as `PART_OF` must not create cycles;
- query direction may be forward or reverse even though storage direction is fixed;
- no friendship, parenthood, employment, or other open-ended real-world predicates;
- no Relation history or version table;
- no automatic AI or rule-based Relation inference.

### Validation

- foreign keys enforce Asset endpoints;
- tests reject self-relations;
- tests reject cycles for hierarchical relations;
- tests verify reverse lookup of children by parent;
- Relation deletion does not delete Assets.

### Rollback

Drop Relation persistence because no existing provider synchronization depends on it.

## Step 8: Consolidate repository contracts and invariants

### Goal

After all entity migrations are stable, review repository operations so they express ADR-001 without introducing a large generic abstraction.

### Constraints

- preserve Repository Pattern and SQLAlchemy 2.x typed ORM;
- preserve explicit transaction boundaries and required flush ordering;
- do not replace focused repository methods with an untyped generic CRUD framework;
- Decision remains responsible for describing intended writes;
- Repository remains responsible for persistence and transactional integrity;
- SyncEngine remains responsible for orchestration and satisfying Requirements;
- no business decisions move into ORM models.

### Validation

- all unit and integration tests pass;
- repository transactions roll back atomically on failure;
- repeated synchronization is idempotent;
- the zero-change synchronization path remains visible in logs and performs no domain writes.

## Step 9: Documentation and final verification

Update architecture documentation only after implementation behavior is verified.

The final V0.2 report must include:

- every modified file;
- every database migration;
- public API changes, if any;
- compatibility decisions;
- tests added or changed;
- commands executed;
- test results;
- unresolved risks;
- confirmation that no out-of-scope feature was added.

## Sequencing rules

- Implement one numbered step at a time.
- A step may be split into smaller commits, but unrelated steps must not be mixed.
- Every step requires review before the next begins.
- If impact analysis shows that the order must change for referential integrity, stop and propose the revised order before coding.
- Do not combine schema migration, broad renaming, matcher redesign, and new persistence entities in one commit.

## Compatibility rules

The following behavior is protected throughout the migration:

- Nextcloud Adapter scanning;
- ProviderFact production;
- content-hash Requirement handling;
- existing file/document identity decisions;
- Decision containing Actions and Requirements;
- SyncEngine orchestration;
- PostgreSQLRepository transaction behavior;
- existing logging of synchronization start, connection, scan, actions, hashes, duration, and completion;
- current unit and integration test behavior unless a test contradicts ADR-001 and is explicitly reviewed.

## Rejected alternatives

### Full rewrite

Rejected because V0.1 already has a real working loop and tested repository behavior. A rewrite would discard validated behavior and make regressions difficult to isolate.

### Implement all five entities in one change

Rejected because it would mix persistence, identity, lifecycle, and API changes into one unreviewable migration.

### Add future Asset types and matchers now

Rejected because types are added only when a concrete Provider and validated use case require them.

### Rename every class and table immediately

Rejected because semantic correctness matters more than cosmetic consistency. Transitional aliases or retained table names are acceptable when they reduce risk.

### Add automatic Tag and Relation generation

Rejected because V0.2 is a domain-model refactor, not an AI interpretation release.

## Consequences

### Positive

- The working V0.1 loop remains the regression baseline.
- Architectural changes are isolated and reviewable.
- Database risk is concentrated in explicit migration steps.
- Future providers can extend AssetType and matcher modules without modifying existing matchers.
- Tag and Relation foundations exist without premature AI policy.

### Costs

- V0.2 requires several small reviewed changes rather than one fast rewrite.
- Transitional compatibility code may temporarily exist.
- Source ownership migration requires careful database backfill and integration testing.
- Some domain entities may exist before they are used by a provider or interface.

## Completion criteria

PDI Core V0.2 is complete only when:

1. all accepted migration steps have been implemented or explicitly marked as verified no-ops;
2. the existing Nextcloud end-to-end synchronization loop passes;
3. all unit and integration tests pass;
4. Domain Model V1 invariants are enforced by code, database constraints, or tested service logic as appropriate;
5. no out-of-scope feature has been introduced;
6. the final implementation report has been reviewed.

## Change policy

This migration plan may be refined after the mandatory read-only impact analysis reveals concrete implementation constraints. Any refinement must preserve ADR-001, remain incremental, and be approved before code changes begin.