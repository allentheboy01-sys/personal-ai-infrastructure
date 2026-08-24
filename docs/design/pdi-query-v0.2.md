# PDI Query V0.2 Design

## Status

Implementation candidate validated locally on 2026-08-12. Final Freeze is not
declared by this document and still requires human review.

## Problem

PDI contains more than 15,000 Resources and is expected to grow beyond
100,000. Increasing the per-call Resource limit would move the scale problem
into the LLM context window. Query V0.2 instead adds bounded database-side
aggregation and stable keyset pagination. `MAX_QUERY_LIMIT` remains 100.

## Architecture

The read path remains:

```text
Consumer
  -> PDI MCP
  -> QueryService
  -> QueryRepository
  -> PostgreSQLRepository
  -> PostgreSQL
```

MCP contains no SQL. QueryService validates public input and owns the opaque
cursor codec. PostgreSQL performs filtering, distinct Resource counting, and
grouping. Existing Resource DTOs and the write pipeline are unchanged.

## Time basis and range

All V0.2 time filters use only:

```text
pdi_first_observed_at
```

This is the time when PDI first recognized and created the Resource record. It
is not capture, upload, user creation, provider creation, or provider
modification time.

The explicit range is half-open:

```text
observed_from <= pdi_first_observed_at < observed_to
```

Inputs must be timezone-aware and are normalized to UTC. Either bound may be
open. Reversed or empty ranges are invalid. An explicit range cannot be
combined with the legacy `days` argument. Day aggregation requires both bounds
and a range no longer than 366 days.

## Aggregation

`aggregate_resources()` and `pdi_aggregate_resources` support one optional,
bounded grouping:

- `provider`;
- `day`;
- `mime_type`; or
- `mime_category`; or
- `person_label`.

With no grouping, `total_count` is the count API and buckets are empty. A
separate count method or MCP Tool is intentionally not added.

Every `total_count` is a distinct Resource count. Aggregation results explicitly
return the time basis, normalized range, applied filters, grouping, total,
buckets, and truncation state. Provider and MIME buckets are ordered by count
descending and key ascending. UTC day buckets are ordered chronologically.
At most 100 buckets are returned and truncation is never silent.

`person_label` is a narrow current-state discovery projection rather than a
Resource-text aggregation. It reads only active non-null
`PersonSource.display_name` values, groups them case-insensitively, preserves a
deterministic Provider spelling for each bucket, and counts distinct canonical
Persons. Its `time_basis` is `current_person_source`; only the optional
Provider-provenance filter is accepted. Resource/time/MIME/path filters are
rejected because they have no honest meaning for this projection. It never
reads OCR, titles, paths, semantic search results, inactive labels, or label
history. The existing 100-bucket bound and truncation signal apply.

## Provider and multi-source semantics

Inactive Sources do not participate in list, search, count, filtering, or
aggregation. Resource detail continues to include active and inactive Sources.

All Source-level predicates are satisfied by one active AssetSource and its
current Blob. Predicates cannot be assembled across Sources.

A Resource counts once globally and once in every matching Provider bucket. A
second Source from the same Provider does not increment that Provider bucket.
A multi-Provider Resource can increment more than one bucket, so bucket sums
may exceed `total_count`. Buckets are Resource counts, never Source counts.

Production currently contains Resources for the `integration-test` Provider.
Query V0.2 reports them truthfully and contains no special exclusion.

## MIME semantics

Exact MIME filtering remains unchanged. `mime_category` is a separate filter
derived deterministically from the lowercase prefix before `/`:

```text
image/jpeg -> image
video/mp4  -> video
```

NULL or empty MIME is `unknown`; a non-empty value without `/` is `other`.
Exact MIME and category cannot be supplied together. There is no media
taxonomy or Provider-specific mapping.

Like Provider buckets, MIME buckets count a Resource once per matching bucket.
A multi-variant Resource may occur in more than one MIME bucket, so MIME bucket
sums are also not necessarily additive.

## Pagination

List and search use keyset cursors and continue to return at most 100 Resources.
The Repository fetches one lookahead row to determine `next_cursor`.

Recent order remains:

```text
pdi_first_observed_at DESC, Resource UUID ASC
```

Search order remains:

```text
Asset.title ASC, Resource UUID ASC
```

The first page fixes `snapshot_to`; later pages always require
`pdi_first_observed_at < snapshot_to`. This prevents normal later writes from
being inserted at the front of an existing page sequence. It is not an MVCC
snapshot: Source activation changes, deletion, and backdated writes may still
change later membership.

The cursor is versioned, URL-safe, bounded, and opaque to Consumers. It binds
the operation, normalized query fingerprint, time range, snapshot, and public
Resource position. Its checksum detects corruption and ordinary modification;
it is not encryption, authentication, or an authorization boundary. V0.2 adds
no cursor secret, JWT, Redis, or server-side cursor store.

## MCP compatibility

The existing Tools retain their names and Resource payloads:

- `pdi_list_recent_resources`;
- `pdi_search_resources`;
- `pdi_get_resource`.

List and search add optional observed-range, MIME-category, and cursor inputs,
plus an additive `next_cursor` result field. Old calls retain the 30-day recent
default, all-time search default, default limit 50, maximum limit 100, and
substring matching behavior. `pdi_get_resource` is unchanged.

One Tool is added:

```text
pdi_aggregate_resources
```

The formal Jarvis profile whitelist therefore contains exactly four PDI Tools.
No additional PDI MCP Tool is enabled. Query V0.2 does not change the wider
Hermes runtime Tool policy.

## Index decision

Before the V0.2 indexes, isolated and production plans used sequential scans
and sorting for the keyset query shape. The implementation adds only:

- `ix_assets_created_at_id` on `(created_at DESC, id ASC)`; and
- `ix_asset_sources_active_blob_id` on `(blob_id) WHERE is_active`.

After upgrade, the isolated plan used the Asset time index and an index-only
active Source lookup. Provider, MIME, and trigram indexes are not added.
Substring search remains a known performance warning and retains its existing
ILIKE semantics.

The migration adds no table or column and makes no world-model change.
It was not run against production during candidate validation. The production
database currently has neither an `alembic_version` table nor the two V0.2
indexes, so deployment must use the existing schema adoption/preflight and
baseline-stamp workflow before upgrading to this revision. Production must not
be treated as already stamped.

## Production scale evidence

The Stage 1 read-only audit observed:

- 15,321 Assets;
- 15,335 Blobs;
- 15,322 AssetSources;
- 15,317 Resources with an active Source;
- one Resource with multiple active Sources; and
- no active multi-Provider Resource at that time.

Indicative single executions were approximately 17 ms for a bounded recent
page, 14-23 ms for 30-day aggregation, and 235 ms for an unlikely substring
search. These observations are not benchmarks. Query V0.2 does not add
trigram, full-text, or semantic search.

## Validation

The local candidate passed:

- QueryService and cursor unit tests;
- PostgreSQL range, aggregation, multi-source, MIME, pagination, and MCP tests;
- migration upgrade, reflection, downgrade, re-upgrade, and autogenerate zero
  diff;
- the complete isolated PostgreSQL suite: 139 collected, 138 passed, one
  expected live-Immich skip, and zero failures;
- `pip check`; and
- `git diff --check`.

The same uncommitted candidate was staged outside the server Git repository
and validated against the production `pdi` database with PostgreSQL
transaction read-only mode enforced. It returned 15,317 active Resources,
truthfully included the `integration-test` Provider, completed Provider, UTC
day, and MIME-category aggregation, and returned two consecutive recent and
search pages without duplicate Resource references. The in-memory MCP Client
observed exactly the four expected PDI Tools.

For the runtime check, the repository candidate config was temporarily
installed into the formal Jarvis profile with the staged candidate MCP code.
Hermes selected Provider aggregation first. An initial unbounded day request
was correctly rejected; Hermes then established a 30-day range, completed
bounded day, Provider, and MIME-category aggregation, and explicitly described
`pdi_first_observed_at` as PDI observation time rather than real-world event
time. The server repository, launcher, and frozen three-Tool profile were
restored after validation; deployment of the four-Tool candidate remains a
Final Freeze action.

## Accepted limitations

- only PDI first-observed time is queryable;
- aggregation supports one grouping per call;
- buckets are bounded and may be explicitly truncated;
- Provider and MIME bucket sums may exceed the distinct total;
- cursor pagination is not an MVCC snapshot;
- substring search remains unranked ILIKE metadata search;
- exact counts scan qualifying data and are not precomputed;
- no Observation, Relation, Event, Memory, semantic search, or content access is
  added.
