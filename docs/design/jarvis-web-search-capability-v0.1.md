# Jarvis Web/Search Capability V0.1

Status: implementation candidate, not production-qualified. No real Search
Provider credential is configured by this source pass.

## Boundary

```text
Hermes Turn
  -> Turn-scoped jarvis_web MCP proxy (stdio; AF_UNIX client only)
  -> /run/jarvis-web-access.sock
  -> jarvis-web-access.service
  -> public Internet / replaceable SearchProvider
```

The proxy exposes exactly `jarvis_web_search(query, limit=5)` and
`jarvis_web_fetch(url)`. It contains no HTTP implementation or Provider
credential. One Hermes bridge process serves one Jarvis Turn and launches one
MCP proxy process, so proxy-process counters are exact Turn-local authority:
two searches, three fetches, three distinct fetched URLs, and two concurrent
fetches. No Turn identifier, time window, or global approximation is added.

The long-lived service owns the global four-operation semaphore, public egress,
DNS and URL validation, transport, deterministic extraction, and Search
Provider credential. IPC is private AF_UNIX only; there is no Web capability
TCP listener. Safe Exec remains network-disabled and PDI remains independent.

## Public Web transport

Only HTTP port 80 and HTTPS port 443 are accepted. Userinfo, alternate schemes,
noncanonical numeric IPv4 forms, internal suffixes, `.ts.net`, and every
non-global address class are rejected. Resolution is performed once per hop;
all A/AAAA answers must be public. The transport then connects to a numeric IP
from that exact set, retains the original hostname for TLS SNI and `Host`, and
verifies the connected peer is still in the pinned set. It never reconnects by
hostname after validation.

Redirects are manual and limited to three. Every target is parsed, resolved,
validated, pinned, and peer-checked again. HTTPS-to-HTTP downgrade and
public-to-private redirect are blocked. Host proxy variables are explicitly
removed from the service environment and the transport does not consult them.

Fetch sends `Accept-Encoding: identity` and accepts only identity or absent
content encoding. HTML, plain text, Markdown, XHTML, and JSON are allowed;
PDF, media, archives, executables, octet streams, and unknown binary content
are rejected. Raw bodies are streamed into bounded chunks up to 2 MiB,
deterministically extracted to at most 20,000 Unicode characters, then fitted
to a 24,000-character structured result. HTML uses the standard non-executing
parser and removes script/style/template-like content; there is no JavaScript,
browser engine, secondary LLM, download, POST exposed to the model, cookie, or
authentication forwarding.

## Search Provider

`SearchProvider` is the stable internal interface. The first adapter uses
Tavily Basic Search through its fixed HTTPS endpoint, Bearer credential, and a
bounded request (`max_results <= 5`, no answer/raw content/images). Provider
JSON is normalized into rank, title, validated canonical public URL, snippet,
optional published time, and retrieval time. Debug payloads never cross the
adapter. Deterministic tests use a fake Provider; provider quality, Chinese and
English relevance, rate/quota behavior, and production credential installation
remain release preconditions.

The only credential reader is `jarvis-web-access.service`, through systemd
`LoadCredential=` and `$CREDENTIALS_DIRECTORY`. Hermes, Jarvis Web, the MCP
proxy, browser, PDI, and Safe Exec receive no Search Provider key.

## Trust, provenance, and telemetry

Fetched content carries `content_trust=untrusted_web`. Hermes policy treats
snippets/pages only as evidence, never instructions or permission, and avoids
sending unnecessary private context to a third-party search service. Residual
model prompt-injection risk remains; isolation and policy reduce but do not
eliminate it.

Web-derived answers must include Markdown source links, with multiple sources
for fresh or disputed claims when available. The existing frontend safely
renders HTTP(S) Markdown links, so V0.1 adds no citation database or UI.
Existing `tool.started`/`tool.completed` events map only to category `web` and
capabilities `search_web` / `read_web_source`; raw query, URL, page, Provider,
arguments, result, and credential remain private. No Runtime event type is
added.

## Service sandbox and residual deployment work

The prepared units use a root-created mode-0660 AF_UNIX socket plus
`DynamicUser`, `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp`,
`PrivateDevices`, `NoNewPrivileges`, empty capabilities, bounded tasks/files/
memory, and inaccessible product databases, home, projects, and Docker paths.
AF_UNIX/INET/INET6 remain because public DNS/TLS are required. Application-level
pinning is primary authority. Kernel private-range egress filtering is deferred
until a host-compatible rule can preserve the local resolver; it cannot replace
application validation.

Production qualification requires a human-owned credential source, immutable
release, actual sandbox/socket activation, bounded Chinese and English Tavily
smokes, provider outage/quota checks, and final privacy/HTTPS acceptance. This
implementation pass does not install, configure, call, or deploy a real
Provider.
