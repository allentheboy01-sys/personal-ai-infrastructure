# PDI Source Observation and Content Evidence Foundation V0.1

## Status and scope

This foundation separates normalized Provider observations from content
evidence. Source-facing Query, Resource Access, enrichment, and MCP projections
now apply the effective Source MIME rule described below. It does not classify
canonical MIME types or backfill existing Sources.

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

The digest-only API remains as a compatibility wrapper. Matcher content paths
that create or select a Blob require complete content evidence. The Sync Engine
calculates the digest and byte length in one Provider body read and carries them
as transient `content_hash` and `content_byte_length` attributes; neither value
is Provider metadata or copied into `AssetSource.metadata`.

New Blob rows use the evidence digest and the byte length from that same stream.
Provider-declared size remains a Source observation and must match the streamed
byte length when content evidence is obtained. A mismatch fails the fact before
any Source or Blob action is applied. Existing Blobs are never rewritten.

Provider version tags are change hints, not content proof. A version change
requires content evidence. A same-version Provider-size change also requires
content evidence, except for the bounded legacy transition below:

- an existing null `provider_size` may be populated without opening content
  when the incoming Provider size equals the attached Blob size;
- if the incoming size differs from the attached Blob size, content evidence is
  required;
- a MIME-only observation change updates the Source without creating or
  mutating a Blob.

After verification, matching digest and byte length update only Source
observations. Different bytes create or reuse a Blob inside the existing Asset.
A matching digest with a different known Blob byte length is an invariant
violation and fails closed rather than mutating or duplicating a same-hash
Blob. A historical `Blob.size = NULL` is treated only as missing legacy
evidence: matching content may continue to reference that Blob without filling
or mutating the historical row. Every newly-created Blob has an evidence size.

`Blob.mime_type` remains transitional legacy-compatible data for existing
consumers. It is not promoted to canonical MIME authority by this work, and a
new Source reusing a shared Blob cannot change it.

For Source-facing Query, Resource Access, and enrichment behavior,
`effective_source_mime_type` is the non-null
`AssetSource.provider_mime_type`; only a null Source observation falls back to
`Blob.mime_type` for legacy migration compatibility. Conflicts always resolve
to the Provider observation. Blob-level views may continue exposing the legacy
Blob field, but it does not decide Source filtering, grouping, access, or
enrichment eligibility. This rule does not define canonical content MIME.

`RequirementType.CONTENT_HASH` remains only as a deliberate compatibility
contract for older requirement producers; the Sync Engine satisfies it through
the same single content-evidence read. Matcher Blob paths use
`CONTENT_EVIDENCE` explicitly.

A future qualified Provider event that explicitly signals content change must
force content evidence even when the version tag is unchanged. This gate does
not add a speculative `ProviderFact` field or implement Nextcloud Activity or
Immich incremental discovery; that signal hook remains deferred with those
batch contracts.

## Deferred work

The following remain deliberately deferred:

- Provider-modified time as a typed Source observation;
- canonical MIME classification and classifier provenance;
- migration or backfill of existing Source observations;
- canonical size semantics beyond the already-frozen Blob content length and
  Source Provider-size observation boundaries.

The legacy bootstrap `schema.sql` and its schema preflight describe the frozen
unversioned V0.1 adoption schema. The additive Alembic revision, ORM metadata,
and migration tests are the current-schema authority for these new columns.
