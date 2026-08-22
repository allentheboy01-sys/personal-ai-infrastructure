# Jarvis Web V0.1.1 — Usability Closure Phase 1

## Status

FROZEN — human usability review approved

2026-08-22

## Canonical conversation state

Production UI conversation state comes only from the existing Jarvis APIs:

- `GET /api/v1/conversations`
- `POST /api/v1/conversations`
- `GET /api/v1/conversations/{id}`

Recent entries are bounded projections of the server-ordered canonical list.
Selecting an entry closes the previous event stream, clears provisional state,
loads the exact persisted Conversation, and records its opaque ID in the URL.
Reloading that URL restores the same Conversation. Review fixtures remain
available only inside the existing explicit review-mode boundary.

New conversation is a frontend reset, not a database write. It removes the
selected Conversation and Turn from UI and URL state. The first subsequent
message creates one canonical Conversation and starts the Turn in that exact
Conversation; later messages reuse it. A later reset cannot retain the prior
Conversation ID through a stale closure.

## Message presentation

Assistant text is rendered as Markdown with raw HTML disabled. Paragraphs,
headings, emphasis, lists, blockquotes, links, inline code, and fenced code are
supported. User text remains plain text. External links opened in a new tab use
`noopener noreferrer`.

Structured `Message.resources` remains the only Resource reference authority.
The browser does not scan prose or Markdown for strings resembling
`pdi:resource:<uuid>`. Structured Agent Resource Cards remain future work until
the Runtime provides a canonical structured reference signal.

## Image representation

Eligible image cards use the Jarvis representation endpoint with
`kind=thumbnail`. Resource Detail uses `kind=preview` only when the canonical
capability advertises preview, and offers an accessible viewport-fitted
lightbox. A failed image request becomes a neutral placeholder rather than a
broken-image icon. Provider URLs and credentials never enter browser models;
all bytes continue through Jarvis and Resource Access.

Video playback and non-image preview are not added. Unsupported resources
continue to state `No preview` truthfully.

## Deferred boundaries

Attachments remain disabled with explicit coming-later semantics. Upload
lifecycle is not inferred. The production Work Panel does not render review
execution fixtures as live telemetry. Video playback, Nextcloud browser
preview, live structured execution telemetry, Context, Memory, Actions, and
Proactive behavior remain out of scope.

No backend API, database schema, Runtime event contract, PDI contract, Exec
sandbox, authentication, deployment, systemd, or Tailscale boundary changes in
this phase.
