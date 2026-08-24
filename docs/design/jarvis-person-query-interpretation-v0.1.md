# Jarvis Person Query Interpretation V0.1

## Scope

This phase grounds natural-language named-person Resource requests against
current Provider labels already preserved by PDI. It adds no family ontology,
alias database, Memory, Person schema, relation model, MCP Tool, frontend
contract, or Runtime protocol.

The authority path is:

```text
user language
→ Hermes Consumer interpretation
→ bounded active-label discovery when needed
→ exact person_label Rich Retrieval
→ existing Resource Result Presentation
```

PDI does not infer that colloquial, familial, translated, or synonymous phrases
refer to a Provider label. Hermes performs ordinary language interpretation,
but may ground the result only against labels returned by PDI.

## Label discovery

The existing `pdi_aggregate_resources` Tool accepts the additive
`group_by=person_label` projection. It returns at most 100 deterministic buckets
derived only from active, non-null `PersonSource.display_name` rows. Labels are
case-insensitively deduplicated and each bucket count is the number of distinct
canonical Persons bearing that active label. An optional `provider` restricts
label provenance.

This projection has `time_basis=current_person_source` and rejects Resource
time, type, MIME, and path filters. It does not inspect Resources,
ResourcePersonRelations, OCR, filenames, titles, semantic search, inactive
sources, or historical labels. No raw PersonSource row or Provider payload is
returned. The generic PDI MCP Tool count remains eight.

## Consumer policy

For a bare or quoted Person name/label-like phrase supplied by the user, Hermes
directly calls `pdi_rich_retrieve_resources` with `kind=person_label`; discovery
is unnecessary. Discovery is reserved for colloquial or relational expressions,
not for confirming an already explicit label.
For a colloquial or relational expression, Hermes first discovers the bounded
current labels and selects only a clearly grounded candidate. Ambiguity causes
clarification, not a sequence of speculative label queries. Discovery is called
at most once for one user intent and the returned bounded candidate set is
reused for the rest of that Turn.

Explicit photo/image language maps to `mime_category=image`; explicit video
language maps to `mime_category=video`. A non-empty, type-appropriate
relation-backed Person result terminates retrieval for that intent. Hermes must
not follow it with alias, Provider-semantic, metadata, OCR, or observation
fallbacks. An empty Person result remains valid and does not authorize semantic
visual matches as evidence of Person membership.

For an unbounded word such as "recent", V0.1 uses existing deterministic bounded
Person candidate order. It neither invents a time window nor reads observations
for every hit.

## Privacy and persistence

Discovered labels and Tool arguments remain private to the model/Tool boundary.
They are not added to Work Panel telemetry, Runtime events, SSE, or generic
logs. ResourceRefs continue through the frozen canonical Resource Result
Presentation path only.

The policy is frontend-local neither in authority nor storage: Hermes performs
Consumer interpretation for one Turn, while Conversation/Message remains
canonical chat state. V0.1 adds no persistent alias store or Memory.
