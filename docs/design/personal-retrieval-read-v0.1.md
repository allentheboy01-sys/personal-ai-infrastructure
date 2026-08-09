# Personal Retrieval Read V0.1 Design

## Status

Frozen for the V0.1 implementation described here. This design adds a read-only
projection and MCP boundary without changing PDI's persisted world model or its
write pipeline.

## Validation record

Final validation was executed on 2026-08-09 against the explicitly isolated
PostgreSQL database `pdi_query_test` as user `pdi_test`.

- Resource Query PostgreSQL integration: 4 passed, 0 failed, 0 skipped.
- All integration tests: 15 passed, 0 failed, 1 skipped. The single skip was the
  live Immich Provider test because live Immich credentials were not configured;
  no PostgreSQL Read Pipeline test was skipped.
- Complete suite: 103 passed, 0 failed, 1 skipped.
- The in-memory MCP Client reached the real MCP Tool, QueryService,
  PostgreSQLRepository, and isolated PostgreSQL database.
- Cross-Source filter stitching was rejected: provider, MIME, path prefix, and
  Source name/path predicates were proven to be jointly satisfied by one active
  Source and its current Blob.
- `pip check` and `git diff --check` passed.

The official MCP Python SDK v2.0.0 stable release and PyPI Production/Stable
metadata were verified. The implementation uses its `MCPServer` and first-class
in-memory `Client` APIs; the dependency remains `mcp>=2.0,<3.0`.

## Goal

Provide the first real read-only path from PostgreSQL through PDI's Query layer
to an MCP client:

```text
PostgreSQL
  -> QueryRepository
  -> QueryService
  -> thin MCP adapter
  -> MCP client / agent runtime
```

The MCP client receives resource metadata. It never receives a database engine,
repository, ORM object, Domain entity, or file content.

## Frozen boundaries

- `Asset`, `Blob`, and `AssetSource` remain the internal persisted world model.
- Resource is a read DTO/projection, not a table, ORM type, or second world
  model.
- The existing write Repository contract and `execute()` path are unchanged.
- Provider adapters, Matcher, Decision, SyncEngine, database schema, and
  migrations are unchanged.
- The existing Jarvis v0.4 tool system is unchanged.
- V0.1 adds no HTTP API, content reading, semantic search, write tools, tags,
  relations, activity history, or provider actions.

## Public resource projection

All V0.1 DTOs are immutable and detached from SQLAlchemy sessions.

`ResourceSourceSummary` contains provider, location, name, MIME type, byte size,
and active state. MIME type and size come from the Blob currently referenced by
that Source. It exposes no Source ID, Blob ID, provider external ID, or raw
metadata.

`ResourceSummary` contains a resource reference, resource type, display name,
PDI first-observed time, and zero or more sources. List and search operations
only return resources with at least one active source, and their source
projections contain active sources only.

`ResourceDetail` contains the same core fields, all active and inactive sources,
and zero or more `ContentSummary` values. Content values represent unordered
variants known to PDI; they are not a version history. A checksum is included as
limited content identity evidence, but no content bytes or internal IDs are
exposed.

PDI currently persists only file facts because Matcher ignores folder facts.
V0.1 therefore reports the conservative resource type `file` and does not infer
types from MIME values.

## Resource reference

The only public identity is:

```text
pdi:resource:<asset-uuid>
```

Formatting and parsing are centralized in the Query layer. Parsing requires the
exact prefix and a canonical UUID value. Invalid references and valid references
to missing resources produce distinct, stable Query errors. The MCP adapter does
not parse references itself and no mapping table is introduced.

## Time semantics

Recent means ordered and filtered by `Asset.created_at`, whose public meaning is:

> The time when PDI first identified and created the resource record.

It is not evidence of when the user created, uploaded, modified, or completed
the resource, and it is not a provider modification time. V0.1 does not add
`provider_modified_at`, `pdi_last_observed_at`, or `time_basis`.

Recent ordering is `Asset.created_at DESC, Asset.id ASC`. Search ordering is
`Asset.title ASC, Asset.id ASC`. Both are deterministic.

## Query contract

The read-only repository protocol adds:

- `list_recent_resources(query)`
- `search_resources(query)`
- `get_resource_detail(asset_id)`

Repository methods return detached Query DTOs, never ORM or Domain objects.
List and search use one asset selection query followed by fixed batch queries for
Blobs and Sources, avoiding per-resource N+1 queries.

The Query Service owns input validation, the fixed maximum limit, days-to-time
boundary conversion, resource-reference parsing, and stable errors. Search text
matches only Asset title, Source name, and Source path. Provider, MIME, and path
prefix are independent filters. No file content is read.

V0.1 uses a default limit of 50 and a maximum limit of 100. `days` and `limit`
must be positive integers. Search text must be non-empty. Optional string filters
must be non-empty when supplied. The only supported resource type is `file`.

## MCP tools

The standalone `pdi_mcp` package exposes exactly three read-only tools:

- `pdi_list_recent_resources`
- `pdi_search_resources`
- `pdi_get_resource`

Tools translate MCP arguments into Query Service calls and explicitly serialize
the resulting DTOs. They contain no SQL and do not construct repositories. A
small process composition root creates the database engine, PostgreSQLRepository,
QueryService, and MCP server. The MCP client can only connect to that server.

Tool failures use stable error codes: `invalid_query`, `invalid_resource_ref`,
and `resource_not_found`.

## Dependency decision

The project targets Python 3.13. V0.1 uses the official maintained Python MCP
SDK, package `mcp`, constrained to the current stable major version 2. The plain
package is sufficient for a server and in-memory client tests; no agent framework
or optional MCP development CLI is required.

## Known limits

- Recent time is PDI record creation time only.
- Resource type is conservatively fixed to `file`.
- List/search exclude resources without an active Source; detail can represent
  zero sources and includes inactive Sources.
- Content variants have no chronological meaning because Blob has no timestamp.
- Search is metadata substring matching, not full-text or semantic search.
- There is no primary Source and Source order carries no preference semantics.
