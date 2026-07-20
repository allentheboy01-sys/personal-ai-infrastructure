# Immich Provider Discovery

Status: Discovery in progress  
Target provider: Immich v3.0.3  
Target branch: `feat/immich-provider`

## Purpose

This document records the discovery work required before implementing an Immich adapter for PDI.

The goal is not merely to call the Immich API. The goal is to verify whether PDI Core can represent a provider whose object model and metadata are substantially richer than Nextcloud's, without making the core Immich-specific.

No schema migration or future domain abstraction is introduced by this document. Any model change must be justified by implementation evidence gathered during discovery.

## Verified API Surface

The following operations have been tested successfully against Immich v3.0.3:

| Operation | Endpoint | Result |
| --- | --- | --- |
| Read server information | `GET /api/server/about` | Successful |
| Search assets | `POST /api/search/metadata` | Successful |
| Download original asset content | `GET /api/assets/{id}/original` | Successful |

Authentication uses the `x-api-key` request header.

The discovery key currently has broad permissions. A production adapter should use a separate key with the smallest permissions required for asset discovery and original-file access.

## Observed Immich Asset Shape

A real image asset returned fields from several distinct concerns.

### Provider identity and location

- `id`
- `ownerId`
- `libraryId`
- `originalPath`

### Original file information

- `originalFileName`
- `originalMimeType`
- `checksum`
- `fileCreatedAt`
- `fileModifiedAt`
- `exifInfo.fileSizeInByte`

### Media information

- `type`
- `width`
- `height`
- `duration`
- `exifInfo`

### Immich application state

- `isFavorite`
- `isArchived`
- `isTrashed`
- `visibility`
- `isOffline`
- `resized`
- `isEdited`
- `duplicateId`
- `thumbhash`

These groups should not be collapsed into a single PDI concept merely because Immich returns them in one JSON object.

## Preliminary PDI Mapping

This mapping is provisional and must be validated against more asset types.

| Immich field | Preliminary PDI destination | Notes |
| --- | --- | --- |
| `id` | `AssetSource.external_id` | Stable provider-side identity for the Immich record |
| `originalPath` | `AssetSource.path` or source metadata | Provider-owned storage path; not a global identity |
| `originalFileName` | Blob candidate data | Original content name |
| `originalMimeType` | Blob candidate data | MIME type of the original content |
| `exifInfo.fileSizeInByte` | Blob candidate data | Original content size |
| `checksum` | ProviderFact fingerprint evidence | Must retain its algorithm; must not be written blindly into a canonical hash field |
| `updatedAt` | Source version candidate | Requires stability testing before use as a version tag |
| `isFavorite`, `isArchived`, `isTrashed`, `visibility` | `AssetSource.metadata` candidate | Provider-specific state, not automatically global Asset state |
| `width`, `height`, `duration`, `exifInfo` | ProviderFact metadata / media metadata candidate | Final ownership remains open |
| `thumbhash`, `resized` | Ignore or source metadata | Primarily Immich presentation and derivative-processing information |

## Checksum Verification

Immich returned the following Base64 checksum for the tested JPEG:

```text
js0B4cvgxvZPg1MYAQygR6r8vQc=
```

Decoding it into hexadecimal produced:

```text
8ecd01e1cbe0c6f64f835318010ca047aafcbd07
```

Downloading the original file and calculating SHA-1 locally produced the same value:

```text
8ecd01e1cbe0c6f64f835318010ca047aafcbd07
```

The original file's locally calculated SHA-256 was:

```text
ddffae31d0aee52e561868254087b98dbd5ee2a499bf68949bb8a333eb8f6556
```

Therefore, for the tested asset:

1. Immich's checksum represents the original file content.
2. The checksum is useful content evidence supplied by the provider.
3. It is not interchangeable with PDI's current SHA-256 content identity.
4. PDI must preserve the fingerprint algorithm alongside the fingerprint value.

## Identity Implications

Nextcloud and Immich provide different levels of evidence.

### Nextcloud

Nextcloud discovery typically provides path, name, size, MIME type, modification data, and ETag information, but may require original-content access before PDI can calculate a canonical SHA-256.

### Immich

Immich already provides a verified SHA-1 fingerprint, original-file metadata, dimensions, and EXIF information.

A possible future identity flow is:

```text
Immich scan
    -> ProviderFact with provider fingerprint (SHA-1)
    -> cheap candidate lookup or exclusion
    -> request original content only when canonical identity is still required
    -> calculate PDI SHA-256
    -> final identity decision
```

This is an optimization candidate, not yet a frozen implementation rule.

## ProviderFact Design Implication

The second provider demonstrates that providers do not expose identical evidence.

A useful ProviderFact model likely needs:

1. A stable common core used by the identity pipeline.
2. Explicitly typed optional evidence, such as content fingerprints with an algorithm.
3. Provider-specific metadata that does not leak directly into the stable PDI domain model.

This does not mean ProviderFact should become an unstructured dictionary. The common identity-relevant evidence should remain explicit and testable, while provider-only details can remain isolated.

## Object Model Still to Discover

The following Immich concepts have not yet been mapped:

- Image assets
- Video assets
- Live Photos
- Albums
- Stacks
- People
- Tags
- Duplicates
- Edited assets
- Archived and trashed assets
- External libraries
- Thumbnails and encoded video derivatives

## Open Questions

### Asset and Blob boundaries

- Does one Immich Asset always correspond to one original Blob?
- Should an edited image be a new Blob attached to the same Asset, a new Asset, or only provider state?
- Should a Live Photo become one PDI Asset with image and video Blobs, or two related Assets?
- Are thumbnails and encoded videos ignored, represented as derived Blobs, or left entirely inside Immich?

### Type ownership

- Should `IMAGE` and `VIDEO` become an `Asset` type?
- Is media type sufficiently represented by Blob MIME type?
- Can a single PDI Asset legitimately contain Blobs with different media types?

`asset_type` remains a schema candidate only. No migration should be created until these questions are answered with real examples.

### Relations and collections

- Should an Immich album become a PDI Relation, a collection concept, provider metadata, or nothing in the first version?
- Should an Immich stack become a Relation between Assets?
- Should detected people become Tags, entities, Relations, or provider-only metadata?

### Lifecycle and state

- What should scanning return for trashed, archived, offline, or deleted assets?
- Can `updatedAt` safely detect source changes?
- How should PDI distinguish an unavailable original from an intentionally deleted source?

### Fingerprints

- Should PDI introduce a typed fingerprint value such as `(algorithm, digest)`?
- Should provider fingerprints be persisted, or only used during one synchronization run?
- Can a provider fingerprint be trusted across Immich upgrades, imports, edits, and external libraries?

## Next Discovery Steps

Before implementing the full adapter:

1. Query and inspect a video asset.
2. Query a duplicate or repeated upload of the same file.
3. Test the same original file in both Nextcloud and Immich.
4. Observe whether identical content can converge to one PDI Blob and two AssetSources.
5. Inspect Live Photo behavior if available.
6. Inspect album and stack API responses.
7. Test archived, trashed, and edited asset states.
8. Confirm pagination behavior with more than one page of assets.
9. Confirm whether `updatedAt` changes for metadata-only edits.
10. Replace the discovery API key with a least-privilege key before production use.

## Current Discovery Conclusion

The initial experiment confirms that Immich can provide a richer ProviderFact than Nextcloud while still fitting the existing high-level pipeline:

```text
Provider
    -> Adapter
    -> ProviderFact
    -> Identity
    -> Decision
    -> Repository
```

The experiment also confirms that provider-supplied fingerprints must retain their algorithm and must not be treated automatically as PDI's canonical content hash.

Implementation should begin only after the remaining Asset/Blob/AssetSource boundaries have enough real evidence to avoid encoding Immich-specific assumptions into PDI Core.
