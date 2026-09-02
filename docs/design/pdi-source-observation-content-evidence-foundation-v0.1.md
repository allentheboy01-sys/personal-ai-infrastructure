# PDI Source Observation and Content Evidence Foundation V0.1

## Status and scope

This foundation separates normalized Provider observations from content
evidence without changing current query, Resource Access, enrichment, or MCP
contracts. It does not classify canonical MIME types or backfill existing
Sources.

## Source observations

`AssetSource.provider_mime_type` and `AssetSource.provider_size` preserve the
normalized MIME type and size reported for that Provider object. They are
Provider observations, not Blob identity or canonical content properties.
Provider-specific metadata remains in `AssetSource.metadata`; the normalized
fields do not replace or reinterpret that raw metadata.

The fields are nullable so existing Sources remain valid after the additive
migration. Existing Blob MIME values must not be copied into them: a Blob may
be shared by Sources whose Providers report different MIME types.

`provider_size` is either `None` or an exact non-negative integer within the
PostgreSQL signed `BIGINT` range. The normalized Matcher and domain model fail
closed on bool, negative, non-integer, or out-of-range values; invalid values
cannot become durable Source or newly-created Blob state.

`ProviderFact` continues to carry these normalized observations in
`attributes["mime_type"]` and `attributes["size"]`. Identity preserves them on
Source creation and update, including when a new Source reuses an existing
content Blob. A changed observation is Source state and must not be classified
as unchanged merely because the Provider version tag is unchanged.

Existing Sources begin with null observations. Their first subsequent trusted
Provider observation is intentionally an `UPDATE_SOURCE`; this is observation
population through a controlled sync, not a migration backfill. Production
rollout must separately review the resulting first-sync update volume.

## Content evidence

`ContentEvidence` contains the SHA-256 digest and exact byte length calculated
from one streamed byte sequence. The calculation does not buffer the complete
body. The byte length is therefore evidence about the same bytes that produced
the digest.

Direct construction validates the SHA-256 hexadecimal shape and requires an
exact non-negative integer byte length. Each bytes-like chunk is normalized
independently, so contiguous and non-contiguous memoryviews are supported while
the input iterable is still consumed exactly once.

This gate keeps the existing digest-only API as a compatibility wrapper. Blob
creation still uses its existing size path until the Matcher evidence policy is
implemented in a later gate; historical Blob rows are not rewritten.

## Deferred work

The following remain deliberately deferred:

- Provider-modified time as a typed Source observation;
- the same-version size-drift content-evidence requirement;
- canonical MIME classification and classifier provenance;
- migration or backfill of existing Source observations;
- switching Query, Resource Access, enrichment, or MCP consumers from Blob
  MIME/size to Source observations.

The legacy bootstrap `schema.sql` and its schema preflight describe the frozen
unversioned V0.1 adoption schema. The additive Alembic revision, ORM metadata,
and migration tests are the current-schema authority for these new columns.
