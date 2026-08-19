# PDI Gmail Provider V0.1

## Stage 1 contract

Gmail ingestion uses the existing typed Resource model. Each enumerable Gmail
Message is represented by one `Asset(resource_type=message)`, one current Blob
containing the exact decoded RAW RFC 2822 bytes, and an `AssetSource` whose
provider identity is `(gmail, message.id)`. Distinct Gmail message IDs never
merge merely because their RAW content hashes match.

V0.1 supports exactly one configured Gmail account. The provider identity
`(gmail, message.id)` is scoped to that single account; V0.1 does not claim
that Gmail message IDs are globally unique across accounts. Multi-account
support is deferred and requires an explicit provider-instance/account
namespace review.

The inventory boundary is a complete `users.messages.list` traversal with
`includeSpamTrash=true`. Missing-source reconciliation is permitted only after
all pages and required per-message metadata reads complete successfully. The
provider-reported estimate is diagnostic and is not completeness evidence.

The source metadata allowlist contains only `internalDate`. Subject is display
metadata only and does not participate in identity. The deterministic
`gmail_metadata` extractor derives `gmail.subject`, `gmail.from`, and
`gmail.to` from RAW bytes and derives `gmail.internal_date` from the bounded
provider signal. Its fingerprint covers the current Blob digest and
`internalDate`.

Gmail is an explicit development/pilot provider selected with
`python -m pdi.main --provider gmail`. It is not part of the implicit provider
set and has no systemd unit or timer. Manual production execution can use the
existing formal runner through `provider.gmail.sync` followed by its dependent
`enrichment.gmail_metadata`; this adds no scheduler or MCP tool. Labels,
thread modeling, attachments as Resources, History cursors,
Person matching, body extraction, and Gmail Resource Access remain deferred.

## Authentication boundary

Runtime authentication uses a protected authorized-user token outside Git and
requests only `https://www.googleapis.com/auth/gmail.readonly`. The adapter
uses `google-auth` plus direct HTTPS requests; it does not require the broad
Gmail discovery client. Secrets and message content must never be logged.

The current Google OAuth application remains in Testing. Its authorization is
suitable for development and a controlled pilot, but its refresh token is not
a permanent unattended production credential. Long-lived OAuth lifecycle is
a production-rollout gate, not part of Stage 1.
