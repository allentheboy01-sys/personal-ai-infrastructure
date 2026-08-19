# PDI Typed Resource V0.1

Status: production active and frozen on 2026-08-19.

## Contract

`assets.id` remains the canonical PDI Resource identity and continues to use
`pdi:resource:<uuid>` as its public reference. The physical `assets`,
`Asset`, and `AssetSource` names are intentionally unchanged.

`assets.resource_type` is a required bounded discriminator with two V0.1
values:

- `file`
- `message`

Existing rows are deterministically migrated to `file`. The final database
schema has no server default, so every post-migration writer must supply the
type intentionally.

Blob and AssetSource schemas are unchanged. Every Source, including a Message
Source, continues to require a Blob.

## Identity

File matching retains its existing content-hash behavior. A new Message Source
uses `(provider, external_id)` as authoritative identity and always creates a
new Message Asset and a Blob owned by that Asset. Two distinct Message Source
identities are not merged merely because their content hashes match.

An existing Message Source remains attached to its original Asset. Content
changes create or reuse a Blob only within that Asset. An incoming fact kind
that disagrees with the persisted Resource type fails explicitly.

## Read and capability boundaries

Generic Resource Query reads and filters the stored type. Existing cursor and
ordering semantics are unchanged.

The following V0.1 capabilities remain explicitly file-only:

- legacy Asset/Jarvis reads;
- Immich semantic and Rich Retrieval;
- thumbnail/preview Resource Access;
- existing enrichment discovery; and
- Immich Resource-Person relation mapping.

Observation and Resource-Person Relation schemas continue to reference
`assets.id` without change. No Gmail provider, predicate, retrieval, resource
access, MCP tool, or scheduling capability is introduced here.

## Production rollout constraint

The migration uses a temporary `file` server default only while adding and
backfilling the column, then removes it in the same migration. Production
rollout must therefore prevent old writer code from running against the final
schema.

Production rollout used bounded writer quiescence under the formal shared batch
lock. Migration `3b1e6f8a4c20` classified all 15,325 existing Resources as
`file`; there were no `message` or NULL rows, and the final column has no server
default. Pre/post legacy digests confirmed no identity or content churn.

The production validation used host-native pytest because the Codex command
sandbox blocks the MCP SDK `Client.call_tool` worker path. The same standalone
and minimal pytest controls complete normally outside that sandbox. The final
host-safe/default suite passed with 454 tests and the isolated PostgreSQL suite
passed with 98 tests and two expected skips.
