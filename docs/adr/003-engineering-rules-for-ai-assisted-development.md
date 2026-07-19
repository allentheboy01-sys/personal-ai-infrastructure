# ADR-003: Engineering Rules for AI-Assisted Development

- **Status:** Accepted
- **Date:** 2026-07-19
- **Scope:** Codex and other AI-assisted implementation work in PDI

## Context

PDI uses AI coding tools to accelerate implementation, but architectural ownership must remain with the project maintainer.

V0.1 was exploratory and successfully established a working end-to-end loop. V0.2 marks a transition from exploratory coding to controlled engineering. From this point onward, AI tools must act as implementation agents rather than autonomous architects.

The principal risk is not that an AI tool cannot write code. The principal risk is that it may make broad, plausible-looking changes that silently alter domain semantics, public interfaces, transaction behavior, or tested assumptions.

## Decision

All AI-assisted implementation in PDI must follow the rules in this ADR.

AI tools may inspect, explain, implement, test, and report. They may not redefine accepted architecture, broaden scope, or substitute convenience for approved design.

## Core principle

```text
Human-approved architecture
  -> explicit implementation specification
  -> AI-assisted implementation
  -> human review
```

Not:

```text
high-level intention
  -> autonomous rewrite
  -> post-hoc explanation
```

## Required workflow

Every architecture-sensitive change must follow this sequence:

```text
1. Read relevant ADRs
2. Perform read-only impact analysis
3. Produce an exact implementation plan
4. Receive approval
5. Implement one bounded step
6. Run tests and verification
7. Report every change
8. Receive review before continuing
```

The implementation agent must not skip directly from a broad request to code changes.

## Step 1: Read before changing

Before editing, the implementation agent must inspect:

- all ADRs relevant to the request;
- current domain models and ORM mappings;
- repository interfaces and implementations;
- call sites of any public interface to be changed;
- tests that define current behavior;
- database migrations and schema assumptions, when persistence changes are involved;
- configuration and entry points affected by the change.

The agent must not rely solely on filenames, summaries, or guessed architecture.

## Step 2: Read-only impact analysis

Before implementation, report:

- exact files that must change;
- exact files that may need change;
- exact files that must not change;
- current behavior being preserved;
- proposed interfaces, class names, function names, and module locations;
- database impact;
- test impact;
- compatibility risk;
- unresolved questions.

If any unresolved question affects architecture or public behavior, stop and ask for a decision.

## Step 3: Implementation specification

The approved implementation specification must define, as applicable:

- names of new or changed classes;
- names and signatures of new or changed functions;
- module and package locations;
- ownership of each responsibility;
- data-flow changes;
- transaction boundaries;
- migration order;
- backward-compatibility strategy;
- validation rules;
- exact tests to add or update.

The implementation agent must follow these names and boundaries unless the repository proves them impossible. In that case, it must stop and report the conflict rather than improvising.

## Scope rules

The implementation agent must:

- modify only files required for the approved step;
- keep each change narrowly scoped;
- preserve unrelated behavior;
- avoid speculative abstractions;
- avoid unrelated cleanup;
- avoid formatting entire files unless necessary;
- avoid dependency upgrades unless explicitly approved;
- avoid renaming public symbols merely for style;
- avoid moving modules unless explicitly approved;
- avoid creating future-facing frameworks not required by the current step.

A useful change is not automatically an in-scope change.

## Architecture protection rules

The implementation agent must not:

- modify a frozen ADR;
- redefine `Asset`, `Blob`, `Source`, `Relation`, or `Tag` semantics;
- add new Asset types without approved domain review;
- add provider-defined dynamic domain types;
- turn Relation into a general knowledge graph;
- add AI-generated Tag or Relation pipelines during the V0.2 refactor;
- make provider lifecycle delete PDI Assets or Blob history;
- merge Decision, Repository, Matcher, Adapter, and SyncEngine responsibilities;
- move business decisions into ORM models;
- replace focused repository behavior with untyped generic CRUD infrastructure;
- rewrite a working module when a local change is sufficient.

If the requested work appears to require any of these, stop and report the conflict.

## Compatibility rules

Unless the approved specification explicitly states otherwise, preserve:

- existing public imports;
- constructor signatures;
- return types;
- error behavior;
- transaction boundaries;
- log meanings;
- configuration keys;
- test fixtures;
- database identity and existing persisted rows;
- existing end-to-end provider synchronization behavior.

When a breaking change is unavoidable, the implementation agent must describe:

1. why compatibility cannot be preserved;
2. every affected caller;
3. the migration path;
4. the rollback path;
5. the tests proving the new behavior.

## Naming rules

Use domain names exactly as accepted by ADRs.

Preferred naming principles:

- nouns for entities and value objects;
- verbs for commands and operations;
- explicit type-specific matcher names such as `FileMatcher`;
- an explicit dispatcher name such as `MatcherRegistry` or `MatcherDispatcher`, selected in the approved implementation specification;
- no ambiguous utility classes such as `Manager`, `Helper`, or `Processor` unless their responsibility is narrowly defined;
- no duplicate concepts under slightly different names;
- no provider name in a Core domain type unless the concept is provider-specific by definition.

Do not rename an existing stable symbol solely to match a preference. Naming changes must have architectural or clarity value greater than their migration cost.

## Class and function design rules

New classes and functions must have one clear responsibility.

The implementation agent must prefer:

- explicit dependencies passed through constructors or function arguments;
- small focused interfaces;
- typed inputs and outputs;
- deterministic domain logic;
- pure functions where state is unnecessary;
- enums for controlled vocabularies;
- repository operations that express domain intent;
- validation near the boundary responsible for enforcing it.

The implementation agent must avoid:

- large `if`/`elif` chains that grow with each Asset type;
- global mutable registries created implicitly at import time;
- hidden database access in domain models;
- broad exception swallowing;
- boolean parameters whose meaning is unclear at call sites;
- generic dictionaries where a stable typed structure already exists;
- premature base classes with only one implementation;
- abstractions introduced solely to reduce a few repeated lines.

## Database and ORM rules

For persistence changes:

- use SQLAlchemy 2.x typed ORM conventions already established in the project;
- preserve explicit foreign keys and uniqueness constraints;
- preserve required `flush` ordering;
- keep transaction ownership in Repository or the approved application boundary;
- do not commit inside low-level helper methods;
- write migrations that preserve existing data;
- separate semantic ownership changes from cosmetic table renames when useful;
- do not drop a column or table until data migration and rollback have been reviewed;
- represent invariants in database constraints when practical and in tested service logic when graph-wide validation is required.

Every schema change must include:

- forward migration behavior;
- existing-row backfill behavior;
- nullability transition, if any;
- rollback or downgrade strategy;
- integration tests against real PostgreSQL when the affected behavior depends on PostgreSQL semantics.

## Testing rules

No approved implementation step is complete until relevant tests pass.

The implementation agent must:

- run existing tests before changing code when practical;
- add tests for every new invariant or branch;
- preserve existing regression coverage;
- prefer behavior-focused tests over implementation-detail tests;
- include integration tests for Repository and PostgreSQL-specific behavior;
- verify idempotency for synchronization and get-or-create operations;
- verify rollback behavior for transactional failures;
- verify zero-change synchronization does not create unnecessary writes;
- report tests not run and the exact reason.

The agent must not:

- delete a failing test to make the suite pass;
- weaken assertions without explaining why the old behavior is invalid;
- replace integration coverage with mocks when persistence semantics are the subject of the change;
- claim success when required tests were not executed.

## Logging rules

PDI synchronization must remain observable.

Changes must preserve or improve logs for:

- application start and stop;
- provider connection;
- provider scan count;
- matching and Requirement satisfaction where useful;
- action count;
- content-hash count;
- transaction failure;
- synchronization completion and duration.

Logs must help locate failures without exposing secrets, credentials, or sensitive content.

Do not add noisy per-record logs by default when aggregate logs are sufficient.

## Security and secrets rules

The implementation agent must not:

- commit `.env` files;
- commit credentials, tokens, passwords, private URLs, or personal data;
- log secrets or full sensitive payloads;
- replace environment-based configuration with hard-coded values;
- weaken TLS, authentication, or authorization settings as an implementation shortcut.

Any discovered secret in tracked files must be reported immediately and not repeated unnecessarily.

## Commit rules

Each commit must represent one coherent approved change.

Commit messages should describe intent, for example:

```text
feat(domain): add controlled asset type
refactor(identity): dispatch matchers by asset type
refactor(source): attach provider source to blob
feat(tags): add minimal tag persistence
```

Avoid commits that mix:

- schema migration and unrelated cleanup;
- multiple ADR migration steps;
- renaming and behavior changes across the whole repository;
- new features and refactoring.

The implementation agent must not push or merge unless explicitly instructed.

## Required implementation report

After every implementation step, report exactly:

### 1. Summary

What was implemented and whether it matches the approved step.

### 2. Modified files

For every file:

```text
path
- what changed
- why it changed
```

### 3. Design mapping

Explain how each change implements the relevant ADR or approved specification.

### 4. Preserved behavior

List important behavior deliberately left unchanged.

### 5. Database impact

List migrations, constraints, backfills, and compatibility behavior.

### 6. Tests

List:

- tests added;
- tests changed;
- commands executed;
- exact results;
- tests not run.

### 7. Risks and unresolved items

State remaining risks honestly. Do not hide uncertainty.

### 8. Diff boundaries

Confirm whether any out-of-scope file or behavior was changed. If yes, explain and request review.

## Stop conditions

The implementation agent must stop before editing when:

- relevant code has not been inspected;
- the request conflicts with an accepted ADR;
- two accepted ADRs appear inconsistent;
- exact database ownership cannot be determined;
- a public API must break but no migration is approved;
- tests reveal a pre-existing failure that makes validation ambiguous;
- implementation requires an unapproved new dependency;
- the requested step cannot be isolated from unrelated changes;
- user data could be lost;
- the repository state differs materially from the provided context.

Stopping and reporting is correct behavior. Guessing is not.

## Review checklist

Before accepting an AI-assisted change, verify:

- [ ] relevant ADRs were followed;
- [ ] scope matches the approved step;
- [ ] every changed file is explained;
- [ ] public API changes are explicit;
- [ ] domain responsibilities remain separated;
- [ ] database migrations preserve data;
- [ ] tests cover new invariants;
- [ ] existing tests pass;
- [ ] logs remain useful;
- [ ] no secrets or personal data were introduced;
- [ ] rollback is possible;
- [ ] no speculative feature was added.

## Rejected alternatives

### Allow the AI tool to choose architecture during implementation

Rejected because plausible local decisions can create long-term inconsistency and silently override accepted design.

### Ask for a complete repository rewrite from a high-level prompt

Rejected because it makes review, regression isolation, and data migration unsafe.

### Combine planning and implementation in one autonomous pass

Rejected because unknown dependencies should be discovered before code is changed.

### Require approval for every individual line

Rejected because it would eliminate the productivity benefit of AI assistance. Approval applies to architecture, scope, interfaces, and implementation steps; the agent may implement details within those boundaries.

## Consequences

### Positive

- AI assistance increases execution speed without owning architecture.
- Changes remain reviewable and explainable.
- Existing working behavior receives explicit protection.
- Database and domain migrations become safer.
- The project remains maintainable by one person.

### Costs

- Implementation begins more slowly because inspection and planning are mandatory.
- AI tools may stop more often when repository reality conflicts with assumptions.
- Broad cleanup must be postponed or proposed separately.
- Reports and tests add work to every step.

## Change policy

These rules apply to PDI V0.2 and later unless superseded by a new ADR.

Temporary exceptions require explicit approval and must be documented in the implementation report. An AI tool may not grant itself an exception.