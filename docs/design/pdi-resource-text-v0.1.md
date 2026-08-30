# PDI Bounded Resource Text V0.1

## Status and boundary

`pdi.resource-text.v1` is a provider-neutral, read-only public application
contract for one bounded text window from a canonical PDI Resource. V0.1 has
one Provider implementation: Nextcloud. MCP exposes the application service as
`pdi_read_resource_text`; MCP does not resolve Sources or perform Provider I/O.

The contract does not change Resource identity, the World Model, persistence,
or Provider sync. Consumers supply only a `pdi:resource:<uuid>` reference and
window bounds. Provider paths, URLs, Source IDs, credentials, and database
objects remain private.

## Complete-content semantics

`document.text_excerpt` is an Observation, not a complete text
representation. This service never uses, joins, or silently falls back to an
excerpt. It reads one actual complete Provider Resource, verifies that body
against PDI's current Blob SHA-256, and only then creates a public text window.
If the complete content cannot be accessed safely, the result is a typed
error.

Eligible V0.1 Sources are active Nextcloud regular-file Sources whose current
Blob MIME type is:

- any syntactically valid `text/*` type, including `text/plain`,
  `text/markdown`, `text/csv`, and `text/x-python`;
- `application/json`; or
- `application/markdown`.

Filename extensions do not make an ineligible MIME type textual. PDF, DOCX,
ODT, generic binary bodies, images, video, OCR, and extracted excerpts are not
supported. They return `text_unavailable` even if a separate Observation
excerpt exists.

## Source and Provider consistency

The repository returns a detached private projection containing only the
Source identity needed for deterministic selection, Provider-relative path,
resource type, MIME type, recorded size, Blob SHA-256, and optional Provider
version tag. It returns active Sources only and never includes credentials.

Eligible Sources are grouped by normalized valid Blob SHA-256:

- no eligible Source returns `text_unavailable`;
- one content identity selects the lexically smallest stable Source ID;
- different current Blob identities return `ambiguous_text_content`.

The selected path comes only from the private Source projection. The caller
cannot supply a URL or path. The Nextcloud adapter performs one authenticated
GET to the safely encoded user-relative WebDAV path, never follows redirects,
and performs no Provider write.

The maximum complete Provider body is 1 MiB. A known recorded size above the
limit fails before network access. Unknown-size or misleading streams are read
only through the limit plus one byte and then fail. The complete raw body is
hashed with SHA-256. It must equal the current PDI Blob digest before any text
is returned. A mismatch or a safe conditional `412` is
`content_changed_since_sync`; `404` and `410` are `text_unavailable`; transport
and `5xx` failures are `provider_unavailable`.

## Text and window contract

After raw-body hash verification, content is decoded strictly as UTF-8 or
UTF-8-SIG. An initial BOM is removed. No line-ending normalization, Latin-1
fallback, or heuristic encoding detection occurs. NUL and Unicode control
characters other than TAB, LF, and CR are rejected as `invalid_text_content`.

The public shape is:

```json
{
  "schema": "pdi.resource-text.v1",
  "resource_ref": "pdi:resource:<uuid>",
  "provider": "nextcloud",
  "media_type": "text/markdown",
  "encoding": "utf-8",
  "source": "provider_access",
  "text": "...",
  "offset_bytes": 0,
  "returned_bytes": 8192,
  "total_bytes": 12000,
  "truncated": true,
  "next_offset": 8192,
  "content_sha256": "<verified raw Provider SHA-256>"
}
```

`offset_bytes` is a byte offset in the canonical UTF-8 public text after BOM
removal, not in raw Provider bytes. The default window is 8,192 bytes, the
maximum is 16,384 bytes, and the minimum is 4 bytes so a valid Unicode
codepoint always makes progress. An offset must be non-negative and on a UTF-8
codepoint boundary. An offset equal to `total_bytes` returns a valid empty
terminal window; a greater or mid-codepoint offset is `invalid_text_window`.
The returned window never splits a codepoint. The service does not
automatically read another window; callers explicitly provide `next_offset`.

`total_bytes` is the UTF-8 byte length of the decoded public representation.
`content_sha256` remains the verified hash of the complete raw Provider body,
including an initial BOM when one exists.

## Stable errors

The public boundary uses sanitized stable codes including:

- `invalid_resource_ref`;
- `text_unavailable`;
- `ambiguous_text_content`;
- `text_too_large`;
- `invalid_text_window`;
- `invalid_text_content`;
- `content_changed_since_sync`;
- `provider_unavailable`;
- `provider_invalid_response`;
- `resource_not_found`; and
- `resource_access_unavailable`.

Errors never serialize Provider URLs or paths, request headers, credentials,
SQL, database details, or stack traces. Missing Nextcloud configuration does
not prevent generic MCP startup: the Tool remains registered and an attempted
read returns `resource_access_unavailable`.

## Non-goals

V0.1 does not add PDF/DOCX extraction, large-file range hashing, image/media
analysis, renderer metadata, agent-runtime integration, filesystem access, or
write operations. Existing Immich thumbnail, preview, and video contracts are
unchanged.
