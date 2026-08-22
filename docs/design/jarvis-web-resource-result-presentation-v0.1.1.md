# Jarvis Web V0.1.1 Resource Result Presentation

## Status

FROZEN — human-approved production release candidate

2026-08-22

## Authority and canonical path

Only ResourceRefs extracted from the successful `structuredContent` of an
actual PDI MCP result have presentation authority. Assistant prose, tool
arguments, textual MCP content, UUID guesses, frontend parsing, and execution
telemetry are never Resource authority.

The canonical path is:

```text
PDI structuredContent
  -> private Hermes bridge result collector
  -> completed.resource_refs
  -> Runtime TURN_COMPLETED.resource_refs
  -> atomic Assistant Message + MessageResourceRef persistence
  -> Conversation PDI hydration
  -> existing ResourceStrip / ResourceCard / detail / preview / lightbox
```

`tool.started` and `tool.completed` remain sanitized process-local telemetry.
They never include ResourceRefs, arguments, results, paths, Provider IDs, or
raw MCP metadata. The terminal SSE record also omits ResourceRefs; the browser
reloads the canonical completed Conversation after the database transaction.

## V0.1.1 presentation rule

Only these result-set-producing tools can replace the presentation snapshot:

- `pdi_list_recent_resources`;
- `pdi_search_resources`;
- `pdi_retrieve_resources`; and
- `pdi_rich_retrieve_resources`.

`pdi_get_resource`, `pdi_get_resource_observations`, and
`pdi_aggregate_resources` remain available to Hermes but do not automatically
attach Resource cards.

Each presentation-producing invocation receives a private result ordinal at
tool-start time. This ordinal is independent from the user-visible, 32-item
execution telemetry counter. The highest successfully extracted ordinal owns
the final snapshot even when concurrent callbacks complete out of order. A
newer successful empty result replaces an older non-empty snapshot; malformed,
failed, or oversized output does not.

The selected snapshot preserves PDI array order, removes duplicates at first
appearance, and is capped at eight canonical `pdi:resource:<uuid>` references.
Results from separate searches are never unioned or UUID-sorted.

## Accepted trade-off

This deterministic V0.1.1 heuristic does not perfectly distinguish an explicit
request to find/show Resources from a question that uses Resources only as
background evidence. Consequently, the last successful result-producing PDI
operation may place up to eight Resource cards under some RAG-style answers.
This is accepted for V0.1.1. No model-selection protocol is introduced.

A possible future design may let the model select a structured subset from an
authoritative PDI-produced candidate set, followed by an exact bridge-side
intersection. The model must never create Resource authority.

## Bounds and failure semantics

- Callback results larger than 1 MiB are not parsed for presentation.
- Extraction uses only fixed tool-specific paths in `structuredContent`; it
  never recursively scans strings.
- A completed Assistant Message contains zero to eight ordered refs.
- More than eight unique refs reaching State is a protocol violation rejected
  before database mutation.
- Failed, cancelled, and interrupted Turns create neither an Assistant Message
  nor MessageResourceRef rows.
- A malformed private final completion record fails closed as
  `bridge_invalid_event`.
- Presentation extraction failure alone does not fail an otherwise valid Turn.
- Missing or temporarily unhydratable Resources omit cards while preserving the
  Assistant body and stored refs; a later reload can retry hydration.

## Unchanged boundaries

This feature reuses `MessageResourceRef` and the existing unified Resource UI.
It adds no migration, PDI tool, Hermes profile capability, Exec authority,
systemd change, Tailscale change, Provider write, or prose parsing path.
