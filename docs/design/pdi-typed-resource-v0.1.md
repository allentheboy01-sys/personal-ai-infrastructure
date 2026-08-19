# PDI Typed Resource V0.1

Status: Stage 1 implementation candidate; not deployed.

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

A later rollout review should use a bounded writer quiesce under the formal
shared batch lock: stop new formal batch entry, wait for the current owner to
finish, fast-forward/install the typed writer, apply the migration, verify the
backfill and constraints, then restore formal execution. No compatibility
framework or dual-write period is part of V0.1.
