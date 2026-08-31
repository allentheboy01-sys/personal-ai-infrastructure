# PDI Bounded Resource Image Preview V0.1

## Status and boundary

`pdi.resource-image-preview.v1` is a provider-neutral, read-only public MCP
contract for one bounded actual image preview from a canonical PDI Resource.
V0.1 has one Provider implementation: Immich. Consumers supply only a
`pdi:resource:<uuid>` reference through `pdi_read_resource_image_preview`.

The MCP adapter delegates ResourceRef validation, private Source resolution,
Provider selection, ambiguity handling, MIME validation, byte limits,
cancellation, and stream closure to `ResourceAccessService`. It does not query
PDI persistence, construct Provider requests, or receive Provider credentials.

## Representation semantics

The public `image_preview` operation maps exactly to
`ResourceRepresentationKind.PREVIEW`. It does not retry a thumbnail, OCR,
metadata, another Provider, or another representation. The existing Resource
Access preview limit is 16 MiB of raw representation bytes, enforced against
both declared length and the actual stream. The service admits a verified
`image/*` media type; PDI does not inherit any particular consumer, model, or
agent runtime's image-MIME policy.

The MCP adapter consumes the bounded stream in memory because standard MCP
image content carries a complete base64 payload. It does not write a temporary
file, cache the payload, or create another persistent image store. The stream
is closed on success, domain failure, or cancellation, and cancellation is not
converted into a partial result.

## MCP contract

The Tool input contains one field:

```json
{
  "resource_ref": "pdi:resource:<uuid>"
}
```

On success, `content` contains exactly one standard MCP image block. Its
`data` is canonical RFC 4648 base64 of the delivered preview bytes, and its
wire `mimeType` is the verified PDI representation media type. The separate
structured result is:

```json
{
  "ok": true,
  "schema": "pdi.resource-image-preview.v1",
  "resource_ref": "pdi:resource:<uuid>",
  "representation": "image_preview",
  "media_type": "image/jpeg",
  "byte_length": 123456
}
```

`byte_length` is the raw preview length before base64 encoding. The structured
result never duplicates image bytes and does not include Provider identity,
Provider locator or URL, Source or database IDs, filesystem paths, request
headers, version metadata, or credentials. It describes the PDI representation
only; a consumer may independently normalize or reject that representation.

## Failure and optional composition

Resource Access domain failures retain their stable sanitized codes, including
invalid ResourceRef, missing Resource, unavailable or ambiguous
representation, Provider failure or invalid response, excessive size, and
unavailable Resource Access capability. An error result contains no image
block or partial base64 payload. Errors must not contain Provider URLs,
locators, credentials, SQL, database details, private Source identities, or
stack traces.

Immich configuration is optional for generic MCP startup. The Tool remains
registered when no Immich Resource Access service is composed; invocation then
returns `resource_access_unavailable`. When the MCP bootstrap owns the Immich
adapter and HTTP client, its lifespan closes that owned runtime exactly once.

## Non-goals

V0.1 does not add image understanding, OCR, model-capability negotiation,
consumer MIME normalization, attachment storage, UI rendering,
consumer-runtime integration, Provider URLs, arbitrary representation
selection, or write operations. Existing thumbnail, preview, and video
Resource Access semantics remain unchanged.
