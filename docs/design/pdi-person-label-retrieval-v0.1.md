# PDI Person Label Retrieval V0.1

## Scope

Person Label Retrieval V0.1 preserves a Provider-declared current Person name
on the existing `PersonSource` and uses the existing
`ResourcePersonRelation` model to retrieve Resources. It does not add a
canonical Person name, family ontology, identity inference, fuzzy matching,
face recognition, or a new MCP Tool.

The first accepted Provider fact is an Immich `/api/people` item whose `name`
is `妈妈`. PDI preserves that exact normalized Provider label. It does not
infer that `我妈`, `母亲`, or any other expression has the same meaning.

## Persistence and lifecycle

`Person` remains exactly `id` plus `created_at`. `PersonSource` adds nullable
`display_name`. The field is current, Provider-derived, and specific to the
source identified by `(provider, external_id)`; it is not a universal name for
the canonical Person.

Provider names are normalized with Unicode NFC and outer whitespace trimming.
A missing, null, empty, or whitespace-only name becomes `NULL`. A non-null,
non-string name invalidates the complete Provider inventory before
reconciliation. Display casing and internal content are preserved.

A successful rename updates the existing PersonSource without changing its
Person identity. V0.1 retains no label history. An inactive PersonSource keeps
its last observed label for provenance, but inactive labels do not participate
in current retrieval. Reactivation restores `inactive_at` to `NULL` and writes
the Provider's current label in the same transaction.

Different ProviderSources may retain different labels for the same Person.
Labels are not unique, and matching labels may identify multiple Persons.

## Retrieval contract

Rich Retrieval adds one first-class `PersonLabelPrimary` variant:

```text
kind: person_label
label: exact Provider-declared label
provider: optional label-provenance restriction
```

The primary normalizes the request with the same NFC and trim rules, rejects
empty input, and performs case-insensitive equality through the indexed
`lower(display_name)` expression. It does not perform substring, fuzzy,
embedding, synonym, or language-relation matching.

Candidates follow this authoritative path:

```text
active matching PersonSource
→ canonical Person identity
→ active ResourcePersonRelation
→ file Resource with an active AssetSource
→ ResourceSummary
```

The ResourcePersonRelation Provider does not need to equal the label-source
Provider. If `PersonLabelPrimary.provider` is set, only label provenance is
restricted; `RichFilters.provider` separately restricts Resource sources.

Candidate ordering is `Asset.created_at DESC, Asset.id ASC`. This is PDI
first-observed ordering and is not media capture time. Existing Rich Retrieval
candidate and result limits remain authoritative, and all existing filters are
reused after candidate generation.

`pdi_search_resources` remains lexical metadata search.
`pdi_retrieve_resources` remains Provider-native semantic retrieval.
`pdi_rich_retrieve_resources` gains the additive primary variant while the
generic MCP Tool count remains eight.

## Indexes

The schema adds two partial indexes:

```text
lower(person_sources.display_name), person_id
WHERE inactive_at IS NULL AND display_name IS NOT NULL

resource_person_relations.person_id, resource_id
WHERE inactive_at IS NULL
```

The second index supplies the reverse Person-to-Resource access path that the
existing Resource-first composite primary key cannot efficiently provide.

## Backfill and write boundary

The additive migration creates no labels and rewrites no identity or relation.
After a separately approved production migration, the existing explicit
`python -m pdi.person_identity` complete scan can populate all current Immich
labels in place. A Resource-Person relation rescan is not required.

Provider writes remain zero. Jarvis has no direct PDI write or database access.
PDI controlled synchronization may write only PersonSource label and lifecycle
state in this phase.

## Consumer boundary

The Consumer may later translate user language into a structured request:

```text
我妈的照片
→ person_label = 妈妈
→ mime_category = image
```

That translation is not part of Person Label Retrieval V0.1. Jarvis continues
to reach the capability only through the existing PDI MCP boundary.
