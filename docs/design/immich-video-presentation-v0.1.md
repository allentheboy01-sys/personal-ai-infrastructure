# Immich Video Presentation V0.1

## Status

Implementation candidate. Human-frozen design; production activation is a
separate review.

## Scope

An ordinary canonical PDI file Resource with an active Immich `video/*` Source
is presented as video. Jarvis renders an Immich-generated thumbnail and a small
play affordance, then uses a browser-native `video` element in Resource Detail.

The browser accesses only Jarvis ResourceRef endpoints:

```text
Browser
  -> Jarvis Web ResourceRef proxy
  -> PDI Resource Access UDS
  -> Immich thumbnail or video playback endpoint
```

Provider locators, URLs, API keys, filesystem paths, and raw provider errors do
not cross the browser boundary.

## Thumbnail contract

`thumbnail` and `preview` remain bounded image representations. Active Immich
image and video Sources are eligible, but the upstream response must still be a
validated `image/*` body and must remain within the existing 2 MiB/16 MiB
limits. A thumbnail failure falls back to a safe video placeholder and does not
affect the canonical assistant answer or Resource detail metadata.

## Playback contract

Playback is separate from the bounded image representation contract:

```text
GET /api/v1/resources/{resource_ref}/video
  -> GET /v1/resources/{resource_ref}/video over private UDS
  -> GET /api/assets/{provider_locator}/video/playback
```

Only a canonical ResourceRef is accepted at the public endpoint. Resource
Access resolves exactly one active Immich file Source with a `video/*` MIME.
The client may provide one syntactically valid byte Range. The proxies preserve
validated `200`, `206`, or `416` status and, where applicable,
`Content-Range`, `Accept-Ranges: bytes`, `Content-Type`, and `Content-Length`.

The stream is pull-driven in bounded chunks and is never materialized as one
body or temporary host file. Stream cancellation closes the upstream response
and releases the shared Resource Access concurrency slot. Jarvis does not
transcode. HLS is not part of V0.1.

## Frozen non-goals

- no `livePhotoVideoId` ingestion or Live Photo inference;
- no HEIC/MOV basename, timestamp, device, or adjacency pairing;
- no Resource identity merge, alias, grouping, relation, or DB migration;
- no Resource Result Collector change;
- no direct browser-to-Immich access;
- no Safe Exec, Hermes, Person Query, Web/Search, or Attachment change.

Image detail/lightbox and non-image/non-video generic presentation remain
unchanged. A future Live Photo phase requires an authoritative provider-derived
Resource relation design.
