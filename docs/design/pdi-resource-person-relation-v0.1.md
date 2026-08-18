# PDI Resource-Person Relation V0.1

## Scope and meaning

Resource-Person Relation V0.1 stores one provider-derived relation:

```text
Resource depicts Person
```

A row means that the named Provider currently supplies evidence that an
existing PDI Resource depicts an existing PDI Person. It is not an independent
PDI face-recognition conclusion, an absolute identity claim, or an inferred
relationship. V0.1 introduces no generic Relation graph, predicate registry,
confidence, face data, bounding boxes, embeddings, public query API, MCP Tool,
or schedule.

## Persistence and lifecycle

`resource_person_relations` contains exactly `resource_id`, `person_id`,
`provider`, and nullable `inactive_at`. Its primary key is
`(resource_id, person_id, provider)`. Resource and Person references use
`ON DELETE RESTRICT`; provider must be non-empty. There is no relation UUID.

Active means `inactive_at IS NULL`. An inactive row means only that this
Provider did not support the relation in its latest successfully completed
reconciliation. It does not mean the real-world relation became false or that
the Resource or Person ceased to exist. Separate Provider rows reconcile
independently.

## Immich inventory and reconciliation

The explicit Immich adapter receives active Immich PersonSource identities and
uses paginated `POST /api/search/metadata` requests with `personIds`. It extracts
only asset IDs and deduplicates asset-person pairs. Normal synchronization does
not call the Faces API, use the sync stream, or read the private Immich database.

Only active AssetSource and PersonSource mappings can produce persisted rows.
All HTTP requests and pagination complete before reconciliation begins. A
partial or invalid inventory cannot inactivate existing relations. One short
transaction performs mapping, composite-key upsert/reactivation, and missing
relation inactivation for that Provider.

Production has 10,574 audited Immich asset-person pairs. Of these, 10,460 map
through the 417 standard enumerable PersonSources and are active in PDI. The
remaining 114 pairs reference 84 Provider Person identities outside Person
Identity V0.1 and are deliberately excluded; no hidden Person or PersonSource
is fabricated.

## Production validation

Alembic head `9c4e1a7b2d30` created the empty table without backfill. The first
explicit sync created 10,460 active relations spanning 5,267 Resources and 417
Persons. Duplicate composite identities and Resource/Person orphans were zero.

An immediate second complete sync reported 10,460 unchanged rows and zero
created, reactivated, or inactivated rows. Row count and aggregate mapping
digest were unchanged. Counts and aggregate digests for Persons, PersonSources,
Assets, Blobs, AssetSources, ResourceStatements, ResourceEnrichments, and
PipelineRuns were unchanged across synchronization.

## Explicit execution

`python -m pdi.resource_person_relation` performs one complete sync and prints
only aggregate counts and duration. Failure output is sanitized. It has no
daemon, retry framework, formal lock, systemd unit, timer, PipelineRun registry
entry, or automatic cadence. Scheduling and consumer exposure remain deferred.
