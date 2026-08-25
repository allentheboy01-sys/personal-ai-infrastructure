# Jarvis Web/Search Capability V0.1

Status: implementation candidate, not production-qualified. DDGS is the
keyless default candidate; Tavily remains an optional credentialed adapter.

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
DNS and URL validation, transport, deterministic extraction, and any optional
Search Provider credential. IPC is private AF_UNIX only; there is no Web
capability TCP listener. Safe Exec remains network-disabled and PDI remains
independent.

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

`SearchProvider` is the stable internal interface. `DDGSSearchProvider` uses
exactly `ddgs==9.15.0` for generic text search. Deployment owns one explicit
backend, the region, moderate SafeSearch, and a five-second provider timeout;
the model controls only query and limit. `auto`, `all`, comma-delimited engine
sets, disabled engines, and unknown names fail closed. The current candidate is
the single `brave` backend with region `wt-wt`; `duckduckgo`, `mojeek`, and
`yahoo` remain bounded deployment choices rather than runtime fallbacks. Each
request creates one DDGS client and runs on one dedicated worker, so synchronous
provider work does not block the async service and provider concurrency is one.
Cancellation of the async waiter cannot forcibly stop a running Python thread;
the concurrency slot therefore remains held until that worker exits.

DDGS search egress is provider-scoped. The only V0.1 endpoint is the externally
owned Xray SOCKS5 listener `socks5://127.0.0.1:10808`; deployment config passes
it explicitly to the `DDGS` constructor. `DDGSSearchProvider` rejects every
other proxy endpoint. Host proxy variables remain removed, and the system
service neither manages nor declares a cross-manager dependency on the
`pdi-xray.service` user unit. Proxy loss becomes a sanitized Provider failure;
there is no direct-DDGS or cross-Provider fallback.

DDGS output is not trusted. Only title, `href`, and body are mapped; publication
time is null. Recognized DuckDuckGo `/l/?uddg=` wrappers are narrowly decoded,
while malformed or unknown tracking forms are dropped. Every resulting URL then
passes the existing public/canonical SearchProvider result validation. DDGS is
search-only: source-page reading still uses the proxy-free pinned direct
fetcher. It needs no Jarvis-side API key, proxy credential, login, cookie,
browser, or persistent Home, but search queries are still disclosed to the
configured public search engine. Keyless service does not imply private or
offline operation, and DDGS reliability is weaker than a contracted API.

The qualification on 2026-08-25 used the approved Xray route and one request per
initial candidate. `bing` was not registered because DDGS 9.15.0 marks it
disabled; `mojeek` and `yahoo` returned generic DDGS failures; `brave` returned
five results. With `brave` and `wt-wt`, the bounded Chinese-current,
Chinese-evergreen, English-current, and English-evergreen matrix returned five
results per query in 1.00--1.52 seconds, followed by two successful stability
samples in 1.20--1.64 seconds. No automatic engine or Provider fallback is
implemented.

`TavilySearchProvider` remains an optional alternative with the same bounded
normalization contract. The base systemd service selects DDGS and has no
credential dependency. A reviewed Tavily drop-in selects Tavily and provides
`tavily-api-key` through systemd `LoadCredential=` and
`$CREDENTIALS_DIRECTORY`; Tavily mode fails closed without it. Hermes, Jarvis
Web, the MCP proxy, browser, PDI, and Safe Exec receive no Search Provider key.
Provider JSON/debug payloads never cross an adapter.

## Trust, provenance, and telemetry

Fetched content carries `content_trust=untrusted_web`. Hermes policy treats
snippets/pages only as evidence, never instructions or permission, and avoids
sending unnecessary private context to a third-party search service. Residual
model prompt-injection risk remains; isolation and policy reduce but do not
eliminate it.

Web-derived answers must include source URLs, preferably standard Markdown
links with meaningful labels and multiple sources for fresh or disputed claims
when available. The frontend safely renders both Markdown links and bare
HTTP(S) URL literals as external links while leaving canonical Message text
unchanged, so V0.1 adds no citation database or structured citation UI.
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

The isolated transient systemd qualification passed with DynamicUser and the
prepared sandbox, AF_UNIX-only IPC, no public TCP listener, the explicit Xray
route, and a real normalized `brave` result. Production qualification still
requires an immutable release and final privacy/HTTPS acceptance. `wt-wt` is
the qualified candidate region; `cn-zh` and
`us-en` remain bounded deployment choices and are never model-controlled. Tavily
qualification additionally requires a human-owned credential source. SearXNG
is deferred unless DDGS stability or quality proves insufficient. This source
pass does not deploy or activate a production Provider.
