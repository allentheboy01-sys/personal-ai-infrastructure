# PDI Person Identity V0.1

## Scope

Person Identity V0.1 maps the standard Immich `/api/people` enumerable
inventory to stable PDI Person identities. It does not attempt to represent
every internal Immich Person row. A source becoming inactive means only that it
was absent from the latest successful enumerable scan, not that Immich proved
the underlying person was deleted.

Person is independent from Resource, Asset, Blob, Observation, enrichment, and
pipeline execution state. V0.1 introduces no relation, face, embedding,
evidence, alias, matching, public reference, query API, MCP Tool, scheduler, or
PipelineRun registry entry.

## Persistence

`persons` contains only a UUID `id` and aware UTC `created_at` instant.
`person_sources` uses `(provider, external_id)` as its composite primary key,
references `persons.id` with `ON DELETE RESTRICT`, and has nullable
`inactive_at`. Active means `inactive_at IS NULL`.

PersonSource has no independent UUID, display name, metadata, status,
confidence, canonical flag, or merge state. Identity never depends on Provider
name, birth date, thumbnail, face or asset count, updated time, or cluster
membership.

## Enumerable inventory and reconciliation

The Immich adapter reads only `/api/server/about` and paginated
`/api/people?withHidden=true`. It validates every returned ID and the complete
pagination shape. The Provider-reported total is retained as an in-memory
diagnostic signal but is not used to fabricate identities or reject a complete
enumerable scan when it differs from the returned item count.

Network discovery completes before persistence begins. Only a fully successful
scan enters reconciliation. New source identities atomically create one Person
and one PersonSource; existing identities retain `person_id`; inactive sources
with the same identity are reactivated. Active Immich sources absent from the
completed result receive an aware UTC `inactive_at`. A failed or partial scan
does not invoke reconciliation.

PostgreSQL transaction-scoped advisory locks serialize the same source
identity before Person creation, while the composite primary key remains the
database invariant. This prevents concurrent duplicate discovery from leaving
either duplicate sources or orphan Persons. Provider inventory reconciliation
also uses a provider-scoped transaction lock and a short transaction after the
HTTP scan.

## Conservative Provider lifecycle

Rename and face-membership changes do not affect identity while the Immich
Person ID remains the same. A disappeared ID becomes inactive; a newly observed
ID creates a new Person. Merge, split, delete, re-clustering, redirect, alias,
and cross-provider continuity are not inferred.

Stage 1 creates the migration and validates isolated persistence only. It does
not apply the migration or import People in production, and it does not add a
formal operational schedule.

## Explicit execution

`python -m pdi.person_identity` is the only V0.1 execution entrypoint. It loads
the existing database and Immich settings, performs exactly one complete sync,
prints aggregate counts and duration, and exits. Failure output is sanitized;
it never prints Person IDs, names, Provider payloads, paths, or credentials.
The entrypoint has no scheduler, daemon, shared-lock, PipelineRun, or retry
behavior. Operational scheduling remains deferred.
