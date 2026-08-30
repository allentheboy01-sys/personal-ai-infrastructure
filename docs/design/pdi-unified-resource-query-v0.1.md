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
- cooperative query budget: 30 seconds, checked between bounded service
  stages and repository pages;
- canonical structured result: at most 64 KiB;

The cooperative budget is not a hard preemptive deadline. The application
service reports `bounded_partial` with `bound_reason="timeout"` when it
observes that the budget has expired. It does not interrupt one blocking
dependency operation. Immich semantic retrieval has its own request timeout;
the current Query/PostgreSQL boundary does not establish an end-to-end hard
30-second deadline. No unsafe background-thread cancellation is used.

The 64 KiB canonical structured bound is the only byte cap in this public
application contract. The previously discussed 8 KiB model-facing projection
is not enforced here and is deferred to the future B2.3 consumer-integration
projection.

The serializer removes whole trailing Resource records to enforce 64 KiB; it
never cuts a record or emits malformed JSON.

`selection_status="complete"` means the requested bounded selection was fully
determined. It does not mean that no lower-ranked match exists beyond the
requested top N. `bounded_partial` means a scan, timeout, or serialized-byte
bound prevented the requested selection from being fully determined. The
optional `bound_reason` is one of the fixed values above.

For relevance-preserving `provider_semantic`, a capped Provider result is
complete only when the Provider returned fewer than the candidate cap or the
filtered ordered candidates are sufficient to fill the requested current
page. If the cap was reached and filters leave fewer than `offset + limit`, the
result is `bounded_partial` with `bound_reason="scan_limit"` because lower
ranked Provider hits might still qualify.

## Snapshot and continuation

Repository-backed internal pages use one query fingerprint and one explicit
PDI-observed watermark for the public call. The watermark freezes new-Resource
membership with respect to the existing query semantics: Resources first
observed after it are excluded from later internal pages. This is not an MVCC
snapshot. Mutable Provider/source/Observation facts may change between public
calls. Provider semantic retrieval makes one Provider call per public query
call and filters its returned ranked candidate set deterministically.

Normal top-N calls use `continuable=false` and always return
`continuation=null`, even when lower-ranked matches exist. Agents should not
page ordinary search requests. An opaque continuation is returned only when
the caller explicitly requests continuable traversal and another buffered
position exists. It is versioned by the shared cursor envelope and bound to the
query fingerprint, observed watermark, scan limit, ordered-selection digest,
and position. The digest is computed before slicing over bounded internal keys
that cover membership, ranking, safe path, ordering time signals, and compact
projection inputs. A continuation recomputes that bounded selection and fails
closed with `invalid_resource_query_continuation` if it changed. It never stores
the raw candidate array in the cursor. Changing any primary, filter, sort, scan
limit, or mutable selection input invalidates continuation.

Thus continuation correctness is provided by the observed watermark, query
identity, and selection-digest revalidation rather than by claiming an MVCC
snapshot. A changed selection returns an error instead of a page that might
duplicate or skip Resources. Changing only the page `limit` does not change the
underlying selection identity.

## Unsafe path availability

Logical Provider paths remain fail-closed. If metadata search returns a
candidate whose match can only be explained by a location that cannot be
safely projected, that unprojectable candidate currently fails the whole query
with `resource_query_projection_error`. It is never exposed or silently treated
as a safe `relative_path`. This is a nonblocking availability debt; candidate
skipping is not part of V0.1 because it would need explicit completeness and
diagnostic semantics.

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
