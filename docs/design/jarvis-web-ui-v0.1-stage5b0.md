# Jarvis Web UI V0.1 — Stage 5B.0 production candidate

## Status

**FROZEN.** The production-candidate SHA is the commit containing this freeze
record and is mechanically recorded in the release `BUILD_INFO`. Production
deployment has not been executed.

## Frozen candidate architecture

`jarvis.web.production` is the only production composition entrypoint. It
requires explicit PostgreSQL, Tailscale identity/origin, immutable static,
Hermes launcher, PDI MCP launcher, and Resource Access socket configuration.
It composes only `HermesRuntimeAdapter`, `MCPPDIClient`,
`ResourceAccessClient`, `TailscaleServeAuth`, Jarvis state, and `create_app`.
There is no mock/unavailable fallback and no request-controlled selector.

The default Vite production build cannot activate deterministic review mode.
Review fixtures remain source/test assets and are enabled only by a dedicated
Vite `review` mode used by the review Playwright composition. Production
Resources, Providers, and Runtime therefore fail closed instead of switching
to synthetic data.

## Artifact and dependency boundary

One clean Git commit builds one versioned release containing the application
wheel, production Vite output, private Hermes bridge, protected launcher,
independent Jarvis migration assets, exact hash lock, `BUILD_INFO`, and
`SHA256SUMS`. The verifier requires the directory, manifest, and build identity
to match one 40-character Git SHA and rejects unlisted, symlinked, test,
browser, or review paths. Production imports installed wheel code, never the
mutable Git checkout.

The CPython 3.13/Linux x86_64 production lock contains only the exact
application dependency closure. Hermes remains in its independent formal venv.
No Node process or `node_modules` belongs in the runtime release.

The immutable payload permission contract is explicit: `root:root` after host
installation, directories `0555`, ordinary files `0444`, and the sole
service-executable `bin/hermes-bridge` `0555`. This corrects the previous
candidate defect where a `0700` launcher became inaccessible to `User=harry`
after root ownership was applied. The verifier rejects mode drift, writable
payloads, root-only launchers, and unexpected executable files.

## Web security and caching

The production CSP keeps scripts and stylesheet elements self-only, permits
inline style attributes needed by the frozen UI, denies workers/objects/frames,
and uses same-origin connections/resources. `index.html` and SPA fallbacks are
`private, no-cache`; hashed Vite assets are private immutable; API, SSE, and
Resource representations remain `private, no-store`.

## Host gates

The unit candidate is one worker at `127.0.0.1:8765`, with access/proxy logs
disabled, control-group cleanup, PrivateTmp, read-only system/home, and explicit
denial of Docker socket, SSH/Codex state, and project directories. It does not
run migrations. Real Serve identity behavior remains a Stage 5B host gate.

Current PostgreSQL loopback `trust` must be replaced by SCRAM and validated
before Jarvis roles are used. The runtime role is DML-only; the frozen UUID
schema uses no sequences. Normal long-term use is also gated on proven
encrypted off-host backup/restore coverage or a separately approved minimal
procedure.

Remaining human-approved Stage 5B host gates are: PostgreSQL loopback SCRAM;
versioned `/opt` runtime/release installation; production Jarvis roles and
database; protected `/etc/jarvis` configuration; migration; actual system-level
unit validation/start; Tailscale Serve/HTTPS and real identity tests; Mac and
iPhone E2E; and the off-host backup continuity decision. These are deployment
gates, not application architecture blockers.
