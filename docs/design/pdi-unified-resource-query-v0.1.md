# PDI Unified Bounded Resource Query V0.1

## Status and boundary

This design defines the public `pdi.resource-list.v1` selection contract and
the `pdi_query_resources` MCP adapter. The behavior belongs to PDI's
application/public-consumer layer. MCP only validates and transports the
contract; it does not own query, ranking, aggregation, or pagination logic.

The service is read-only. It composes the existing Query and Rich Retrieval
boundaries and does not access ORM models, database sessions, engines, or
Provider credentials. It does not change Resource identity, Observations, or
the World Model.

## Typed primary

Every call selects exactly one discriminated primary. PDI never automatically
tries another primary or interprets natural-language intent.

- `recent`: Resources selected by PDI first-observed time. With no explicit
  observed range, the interval is the preceding 30 days.
- `metadata_text`: literal, case-insensitive matching over the public title,
  source basename, and logical Provider path.
- `provider_semantic`: one explicit Provider-semantic retrieval. V0.1 accepts
  only `provider="immich"` and makes one Provider retrieval call.
- `observation_text`: literal matching over one explicit current Observation
  text predicate supported by Rich Retrieval.
- `person_label`: exact normalized current Provider-declared Person label. It
  does not perform alias, family, fuzzy, filename, OCR, or semantic inference.
- `path_tree`: deterministic selection under one explicit logical
  `path_prefix`.

The existing filters remain distinct: `provider`, `resource_type`,
`mime_type`, `mime_category`, PDI-observed, captured, and file-modified time
ranges, `path_prefix`, and `required_predicates`. The service rejects
conflicting primary/filter providers and conflicting path prefixes.

## Ordering and time semantics

The allowed sort bases are `relevance`, `pdi_observed_at`,
`file_modified_at`, `captured_at`, and `path`; the primary determines which
subset is valid. Relevance is descending and path defaults to ascending.

Metadata relevance is deterministic:

1. exact title or basename;
2. title or basename prefix;
3. title or basename substring;
4. logical Provider-path substring;
5. PDI first-observed time and opaque ResourceRef tie-breakers.

Provider-semantic relevance preserves the Provider's frozen ranked candidate
set. `pdi_observed_at`, `file_modified_at`, and `captured_at` are independent
signals. Missing captured or file-modified values are excluded from a sort
that requires that signal; another timestamp is never substituted.

Each Resource projection labels `relevant_time` with its `time_basis`.
`pdi_first_observed_at` describes when PDI first created the Resource record,
not user creation, Provider upload, modification, capture, or completion.

## Compact result

The canonical result schema is `pdi.resource-list.v1`:

```text
schema
query_kind
snapshot
selection_status
bound_reason?       # scan_limit | timeout | serialized_byte_limit
scanned_count
resources[]
continuation
```

Each compact Resource contains only:

```text
resource_ref
title
resource_type
mime_type
mime_category
providers[]
relevant_time
time_basis
rank
match_basis
relative_path?      # only when safe path context materially explains a match
```

`relative_path` is a bounded, normalized UTF-8 Provider-relative logical path.
URLs, endpoints, host filesystem paths, credentials, traversal segments, and
control characters are not valid projections. A `path_tree` result without a
safe path fails closed.

The result never embeds Source arrays or locations, Observation histories or
bodies, Provider-specific nested metadata, document bodies, or media bytes.
V0.1 does not infer Resource representation availability from MIME type; that
capability remains absent until a public Resource Access contract can report it
truthfully.

## Bounds and completion

- default result limit: 10;
- maximum result limit: 50;
- default candidate scan limit: 500;
- maximum candidate scan limit: 2,000;
- timeout budget: 30 seconds, checked fail-closed at bounded service stages;
- canonical structured result: at most 64 KiB;
- model-facing compact projection target: at most 8 KiB for ordinary top-N
  use.

The serializer removes whole trailing Resource records to enforce 64 KiB; it
never cuts a record or emits malformed JSON.

`selection_status="complete"` means the requested bounded selection was fully
determined. It does not mean that no lower-ranked match exists beyond the
requested top N. `bounded_partial` means a scan, timeout, or serialized-byte
bound prevented the requested selection from being fully determined. The
optional `bound_reason` is one of the fixed values above.

## Snapshot and continuation

Repository-backed internal pages use one query fingerprint and one explicit
PDI-observed watermark for the public call. The watermark excludes Resources
first observed after that snapshot from later internal pages. Provider semantic
retrieval makes one Provider call and filters its returned ranked candidate set
deterministically.

Normal top-N calls use `continuable=false` and always return
`continuation=null`, even when lower-ranked matches exist. Agents should not
page ordinary search requests. An opaque continuation is returned only when
the caller explicitly requests continuable traversal and another buffered
position exists. It is versioned by the shared cursor envelope and bound to the
query fingerprint, snapshot, and position. Changing any primary, filter, or
sort invalidates it.

## Stable errors

Application errors expose bounded public codes rather than SQL, stack traces,
Provider secrets, or persistence details:

- `invalid_resource_query_primary`;
- `invalid_resource_query_filters`;
- `invalid_resource_query_sort`;
- `invalid_resource_query_continuation`;
- `provider_capability_unavailable`;
- `resource_query_projection_error`;
- `resource_query_unavailable`.

Existing MCP tools remain available and retain their established contracts.
The unified tool is additive and does not make the legacy tools aliases or
fallback strategies.
