# Jarvis Web Consumer Policy

Use PDI as the authority for personal-resource claims. For a named person in a
resource request, prefer relation-backed `pdi_rich_retrieve_resources` with a
`person_label` primary; semantic visual similarity is not proof that a Person
depicts a Resource.

- If the request directly names a person with a bare or quoted name/label-like
  phrase, treat that phrase as the explicit label and use it directly. Do not
  discover labels first merely to confirm an explicit label.
- For a colloquial or relational expression, first call
  `pdi_aggregate_resources` with `group_by=person_label`, then ground the
  expression only against the bounded active labels returned by PDI. Make at
  most one label-discovery call for the same user intent and reuse that
  candidate set. Never fabricate or blindly try alternate labels.
- If more than one current label is plausibly consistent and there is no
  reliable single choice, ask the user to clarify instead of trying each one.
- Map an explicit photo, image, or picture request to
  `filters.mime_category=image`; map an explicit video request to
  `filters.mime_category=video`.
- After an exact grounded `person_label` retrieval with an explicit supported
  `filters.mime_category` successfully executes, its result is authoritative
  for that typed intent whether non-empty or empty; stop retrieval for that
  intent. A successful empty result is not a Tool failure. Preserve the MIME
  constraint: do not retry with an unfiltered `person_label`, an alternate
  label, or semantic, metadata, OCR, or observation fallback merely because
  the constrained result is empty. Broaden only when the user explicitly asks.
- If grounding is unknown or ambiguous before that typed retrieval, discovery
  or clarification remains appropriate. An actual Tool failure may use the
  existing error-recovery path; it is distinct from a successful empty result.
- For "recent" without an authoritative time window, use the deterministic
  bounded order of the relation-backed query. Do not invent a duration or read
  observations for every hit.

These rules add no family ontology, persistent alias memory, or PDI inference.
Do not reveal discovered label lists, tool arguments, raw results, provider
internals, ResourceRefs, or private reasoning in execution telemetry.
