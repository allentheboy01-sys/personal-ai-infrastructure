# Jarvis Runtime Server V0.1

## Status

Final Freeze completed on 2026-08-11 after implementation, server validation,
and human review.

## Validated server result

The formal `pdi-server` deployment passed the following gates:

- Hermes Agent `0.10.0` installed from immutable commit
  `1dd6b5d5fb94cac59e93388f9aeee6bc365b8f42` in its isolated Python 3.13
  environment;
- Hermes import, CLI, MCP client import, and `pip check`;
- Hermes MCP `1.29.0` isolated from PDI MCP `2.0.0`;
- DeepSeek API reachability and authentication;
- `deepseek-v4-flash` model discovery, plain inference, and automatic Tool
  Call generation;
- production database identity `pdi` and a real read-only PDI MCP call;
- exactly three enabled Runtime Tool definitions, all supplied by PDI MCP;
- parent/child environment isolation and no Runtime secret persistence;
- the three natural-language E2E scenarios documented below;
- native session resume and clean new-session behavior;
- on-demand SSH execution with no Runtime daemon or listener; and
- the complete isolated PostgreSQL regression: 119 collected, 118 passed,
  one expected live-Immich skip, and zero failures.

### Natural-language E2E evidence

In one native Hermes session, the user asked:

```text
PDI 最近首次发现了哪些资源？
```

Hermes automatically called `pdi_list_recent_resources`, returned real
production Resources, and explicitly distinguished PDI first-observed time
from photo capture, upload, and modification times.

The user then asked:

```text
帮我找 CURRENT_CONTEXT 相关的资源。
```

Hermes automatically called `pdi_search_resources` and returned the real
Nextcloud Resource `CURRENT_CONTEXT.md` with public reference
`pdi:resource:f4bb286d-5b01-4e53-8d55-c08a5776870a`.

Without repeating that reference, the user continued:

```text
查看这个 Resource 的来源。
```

Hermes reused the conversational reference, called `pdi_get_resource`, and
returned the active Nextcloud source at `CURRENT_CONTEXT.md`.

After a normal exit, `jarvis -c` restored the same session and its context.
A default `jarvis` launch created a different session without loading previous
conversation history; a Resource query in that new session performed fresh PDI
search and detail Tool calls.

## Architecture

```text
Mac Terminal
  -> SSH
  -> pdi-server
  -> jarvis
  -> Hermes Agent 0.10.0
       |-> DeepSeek API
       `-> PDI MCP (stdio)
             -> QueryService
             -> PostgreSQLRepository
             -> production PostgreSQL
```

SSH is the access interface, not part of the Runtime/PDI architecture. Hermes
is the validated Reference Runtime and remains replaceable. DeepSeek is the
current remote LLM provider and also remains replaceable. PDI depends on
neither; MCP is the stable read-only boundary.

## Formal runtime host

The formal host is `pdi-server`, accessed as Unix user `harry` over SSH. The
PDI repository remains `/srv/projects/PDI`, its Python interpreter remains
`/srv/projects/PDI/.venv/bin/python`, and its production database is local to
the server. Jarvis does not require a PostgreSQL tunnel or a Mac-hosted Runtime.

## Runtime lifecycle

V0.1 is an on-demand CLI:

```text
ssh -> jarvis -> conversation -> exit -> process exits
```

There is no Jarvis service, timer, daemon, gateway, listener, HTTP API,
WebSocket endpoint, or automatic startup. Provider Sync continues independently
under its existing server units.

## Hermes version and environment

Hermes Agent is installed in its own virtual environment:

```text
/home/harry/.hermes/hermes-agent/venv
```

The deployment pins official `NousResearch/hermes-agent` release
`v2026.4.16`, version `0.10.0`, at immutable commit:

```text
1dd6b5d5fb94cac59e93388f9aeee6bc365b8f42
```

Install the MCP extra. Do not install from an unpinned branch or latest
release, copy a developer checkout, or install Hermes into the PDI virtual
environment. The Hermes environment keeps its compatible MCP 1.x dependency;
the PDI environment keeps its existing MCP 2.x dependency.

## Formal profile

The formal profile is:

```text
/home/harry/.hermes/profiles/pdi-server
```

Install the repository artifacts as follows:

| Repository source | Server target | Mode |
|---|---|---:|
| `deployment/jarvis/config.yaml` | `~/.hermes/profiles/pdi-server/config.yaml` | `600` |
| `examples/hermes-pdi-poc/SOUL.example.md` | `~/.hermes/profiles/pdi-server/SOUL.md` | `600` |
| `deployment/jarvis/pdi-mcp` | `~/.hermes/profiles/pdi-server/bin/pdi-mcp` | `700` |
| `deployment/jarvis/jarvis` | `~/.local/bin/jarvis` | `700` |

The profile and its `bin` and `sessions` directories must be private to
`harry` (`700`). State, history, session, and authentication files must be
private (`600`) where their file type permits it.

## Secret authority

The only formal Jarvis Runtime secret authority is:

```text
/etc/pdi/jarvis.env
```

It is owned by `harry:harry`, has mode `600`, and contains only the
`DEEPSEEK_API_KEY` assignment. Never place the value in Git, YAML, SOUL,
`auth.json`, a command argument, shell history, or logs. Use
`deployment/jarvis/jarvis.env.example` only as a sanitized shape reference.

PDI retains its separate secret authority at `/etc/pdi/pdi.env`. Do not source
that file into the Hermes parent process.

## Environment isolation

`~/.local/bin/jarvis` starts Hermes with a clean, minimal environment. Hermes
receives `DEEPSEEK_API_KEY` but does not receive `DATABASE__URL`, Nextcloud
credentials, or Immich credentials.

The wrapper applies `umask 077` before starting Hermes so newly created state,
history, session, and log files remain private to the Runtime Unix user.

The profile-local `bin/pdi-mcp` launcher separately reads `/etc/pdi/pdi.env`
and starts PDI MCP with only `DATABASE__URL` plus minimal process variables.
The child does not receive the DeepSeek key or Provider credentials.

This split ensures that Hermes cannot query PostgreSQL directly and PDI MCP
cannot access the LLM credential.

## DeepSeek provider and model

The profile uses the official OpenAI-compatible endpoint:

```text
https://api.deepseek.com/v1
```

The validated current model is `deepseek-v4-flash`. Server-side authentication,
model discovery, plain inference, and automatic Tool Calls passed on
2026-08-11. This is not a permanent model selection. If the candidate becomes
unavailable, stop and obtain a human model decision; do not silently substitute
another model.

PDI metadata and user prompts used in a conversation are sent to the remote
DeepSeek API for inference. PDI data storage stays on the PDI server, but it is
incorrect to describe all Jarvis processing as local.

## Read-only PDI tool surface

The profile enables only the `pdi` MCP platform and exactly these tools:

- `pdi_list_recent_resources`
- `pdi_search_resources`
- `pdi_get_resource`

MCP Resources wrappers and Prompts wrappers are disabled. Filesystem, browser,
shell, scheduler, memory, write, GitHub, email, and calendar tools are not
enabled. The profile adds no MCP server other than PDI.

`pdi_first_observed_at` means the time PDI first recorded a Resource. It is not
the user's creation, upload, modification, or completion time.

## Memory and sessions

The profile explicitly sets both `memory.memory_enabled` and
`memory.user_profile_enabled` to `false`. Long-term memory, memory extraction,
profile inference, and automatic memory save are outside V0.1.

Hermes native conversation sessions remain enabled. Session persistence is not
Jarvis Memory:

- `jarvis` starts a new session;
- `jarvis -c` resumes the most recent session;
- `jarvis --resume <id>` resumes a named session ID;
- `jarvis sessions list` lists saved sessions.

A new session must not infer or recall content from another session.

## User commands

From a fresh SSH login:

```bash
jarvis
jarvis -c
jarvis --resume <session-id>
jarvis sessions list
jarvis mcp list
```

The wrapper selects the `pdi-server` profile and forwards arguments unchanged.
The optional Mac convenience alias below carries no secret and is not installed
automatically:

```bash
alias jarvis-remote='ssh -t harry@pdi-server jarvis'
```

## Manual installation

All repository artifacts are authoritative. Transport an uncommitted candidate
to a private staging directory only after local syntax and secret review.

1. Create `/home/harry/.hermes/hermes-agent/venv` with server Python.
2. Install Hermes from the immutable commit with its MCP extra.
3. Verify Hermes import, CLI version, MCP client import, and `pip check`.
4. Create the `pdi-server` profile and private `bin` directory.
5. Install `config.yaml`, the frozen SOUL example, and `pdi-mcp` with the modes
   shown above.
6. Install the `jarvis` wrapper in `/home/harry/.local/bin` with mode `700`.
7. Have a human securely install `/etc/pdi/jarvis.env` as `harry:harry`, mode
   `600`, without revealing the value.
8. Validate the DeepSeek model gate, PDI MCP tool surface, real read calls,
   environment isolation, session behavior, and a fresh SSH user experience.

For an update, change the pinned commit only through a separately reviewed
Runtime change. Rebuild the isolated Hermes environment, validate it in
staging, and atomically replace the installation. Never update in place from
an unpinned branch.

## Validation checklist

- Hermes reports version `0.10.0` and passes `pip check`.
- Hermes and PDI use separate virtual environments and MCP major versions.
- DeepSeek authentication, candidate model, and tool calls pass.
- The PDI MCP launcher reaches database `pdi`, never a test database.
- PDI exposes exactly the three approved tools and returns a real Resource.
- Hermes parent and PDI MCP child satisfy the environment boundary.
- Natural-language recent, search, and detail calls use the expected tools.
- Follow-up context survives `jarvis -c`; a new `jarvis` session starts clean.
- `auth.json`, session files, console output, and logs contain no credentials.
- No Jarvis daemon, service, timer, cron job, or network listener exists.

## Troubleshooting

- `jarvis: cannot read /etc/pdi/jarvis.env`: install the secret file with the
  required owner and mode.
- `DEEPSEEK_API_KEY is not configured`: the assignment exists but is empty.
- `Hermes runtime is not installed`: build the pinned isolated environment.
- `pdi-mcp: cannot read /etc/pdi/pdi.env`: restore the existing PDI secret
  authority; do not copy its value elsewhere.
- PDI tools unavailable: verify the profile launcher path, PDI environment,
  stdio process, and production database identity without printing secrets.
- Model authentication or model-name failure: stop; do not change models
  without human approval.
- `jarvis` missing after installation: start a new SSH login and confirm
  `~/.local/bin` is on `PATH`.

## Rollback

Rollback affects only the on-demand Jarvis Runtime:

1. Ensure no interactive `jarvis` process is running.
2. Remove or quarantine `~/.local/bin/jarvis`.
3. Remove or quarantine `~/.hermes/profiles/pdi-server`.
4. Remove or quarantine the isolated Hermes environment.
5. Retain or securely remove `/etc/pdi/jarvis.env` according to the human
   secret-management decision.

Do not modify PDI, PostgreSQL, Provider Sync services, timers, or their secret
authority during Runtime rollback.

## Accepted V0.1 limitations

- SSH CLI only and one Unix user;
- on-demand execution only;
- DeepSeek remote inference;
- Hermes native session persistence;
- no Web UI or multi-client session service;
- no daemon or automatic Runtime startup;
- no Memory or proactive behavior; and
- no write tools.

The CLI/MCP boundary remains compatible with a future Web UI, which could call
the same Runtime/PDI contract. V0.1 does not implement or design that Web layer.
