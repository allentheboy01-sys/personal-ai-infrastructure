# Jarvis Runtime Integration V0.1

## Status

FINAL FREEZE

2026-08-09

Final Freeze was confirmed by human review.

## Purpose

Validate that a mature, replaceable runtime can use PDI's stable MCP consumer
boundary to perform natural-language Personal Retrieval against the real PDI
Personal Digital World.

## Architecture

```text
User
  -> Runtime
  -> MCP
  -> PDI Query
  -> PostgreSQL
  -> Resource
  -> Runtime
  -> User
```

The Runtime depends on PDI's read-only MCP boundary. PDI does not depend on the
Runtime or on Hermes.

## Reference Runtime

Hermes Agent 0.10.0 was the Reference Runtime used for this validation. It is a
validated PoC runtime, not a permanent decision for Jarvis. Future runtimes may
replace it while preserving the MCP consumer boundary.

The validated model was a tool-calling model reached through an
OpenAI-compatible provider. Neither the model nor its provider is frozen by
this record.

## Environment Isolation

The two Python environments remained independent:

```text
Hermes
  Python 3.11.15
  MCP 1.27.0

PDI
  Python 3.13.9
  MCP 2.0.0
```

Hermes started PDI MCP over stdio with PDI's own absolute Python executable:

```text
<PDI_PYTHON> -m pdi_mcp
```

Hermes was not installed in the PDI environment, and PDI's MCP dependency was
not changed for Runtime compatibility.

## Exposed PDI Tools

The Reference Runtime exposed exactly three read-only PDI tools:

- `pdi_list_recent_resources`
- `pdi_search_resources`
- `pdi_get_resource`

Hermes MCP Resources and Prompts wrappers were disabled. No other MCP server or
Runtime tool was enabled for the validation.

## Acceptance Evidence

### Test 1: recent Resources

User prompt:

```text
PDI 最近首次发现了哪些资源？
```

Hermes automatically selected `pdi_list_recent_resources`, received real
Resources from PDI, and described their timestamps as PDI first-observed times
rather than user creation, upload, or modification times.

### Test 2: metadata search

User prompt:

```text
帮我找 CURRENT_CONTEXT 相关的资源。
```

Hermes automatically selected `pdi_search_resources` with
`query=CURRENT_CONTEXT`. The real Nextcloud Provider Resource returned by PDI
was:

```text
resource_ref: pdi:resource:f4bb286d-5b01-4e53-8d55-c08a5776870a
resource_type: file
display_name: CURRENT_CONTEXT
provider: nextcloud
location: CURRENT_CONTEXT.md
mime_type: text/markdown
```

The Resource entered PDI through the normal NextcloudAdapter, Matcher,
Decision, SyncEngine, and PostgreSQLRepository write path. It was not a fixture
or a direct database write.

### Test 3: conversational Tool chaining

In the same Hermes session, the user continued without repeating the Resource
reference:

```text
查看这个 Resource 的来源。
```

Hermes resolved “this Resource” from conversation context, reused
`pdi:resource:f4bb286d-5b01-4e53-8d55-c08a5776870a`, automatically called
`pdi_get_resource`, and returned the active Nextcloud Source for
`CURRENT_CONTEXT.md`.

## Time Semantics

`pdi_first_observed_at` means:

> The time when PDI first identified and created the Resource record.

It is not evidence of:

- user creation time;
- user upload time;
- user modification time;
- Provider modification time; or
- when the user completed work.

## Failure Scenarios

The Reference Runtime preserved stable PDI error meaning and did not crash for:

- `invalid_resource_ref`;
- `resource_not_found`; and
- an unavailable MCP process.

When PDI MCP was unavailable, the Runtime reported that the service was
unavailable rather than fabricating Resource data.

## Boundary

This validation contains no:

- Runtime-to-database access;
- Runtime-to-Repository access;
- Runtime-to-ORM access;
- PDI-to-Hermes dependency;
- new PDI Tool or changed Tool contract;
- Resource DTO, Query Service, schema, or migration change; or
- PDI Python dependency on Hermes.

## Non-goals

V0.1 does not include:

- Memory, Observation, Reflection, Planning, or proactive behavior;
- reminders or scheduling;
- write-capable MCP tools;
- relations;
- semantic search, vectors, or RAG;
- a Jarvis UI;
- multi-agent operation; or
- recursive Provider scanning.

## Regression Evidence

Final Freeze preparation used the isolated PostgreSQL database
`pdi_query_test` as user `pdi_test` through the existing database safety guard.
The complete repository suite passed with 103 passed and 1 skipped. The single
expected skip was the live Immich integration test because live Immich
credentials were not configured.

## Conclusion

A mature Runtime has been proven capable of using PDI's stable MCP consumer
boundary to retrieve real Resources from the user's Personal Digital World and
produce grounded natural-language answers.

This result validates the replaceable Runtime boundary. It does not permanently
select Hermes as the Jarvis Runtime.
