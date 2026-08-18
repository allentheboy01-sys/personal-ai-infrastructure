# Codex CLI on `pdi-server`

## Decision

Primary PDI Codex development runs on `pdi-server`, close to the real Linux
runtime and isolated PostgreSQL test infrastructure. Development uses a
separate user-owned checkout. The production checkout remains deploy-only.

```text
~/projects/personal-ai-infrastructure   development and tests
/srv/projects/PDI                      production deployment only
```

This separation is mandatory even though both checkouts are on the same host.

## Verified host baseline

Verified on 2026-08-17:

- host: `pdi-server`;
- OS: Debian 13, x86_64;
- user: `harry`;
- shell: Bash;
- Git and curl available;
- production checkout clean and aligned with `origin/main` at inspection time;
- `~/.local/bin` is added to `PATH` by the existing Bash profile once the
  directory exists; and
- Node/npm are not required when using the standalone Codex binary.

## Install and update

Current host status (2026-08-17): Codex CLI `0.147.0` is installed at
`~/.local/bin/codex`. Because the host could not reach the ChatGPT installer
and OpenAI release CDN, installation used the official
`@openai/codex@0.147.0-linux-x64` npm platform artifact. Its registry-published
SHA-512 integrity was verified before extraction. The complete platform bundle,
including sandbox resources, bundled `rg`, zsh, and code-mode host, is kept
under `~/.local/share/codex/0.147.0`.

The host now has a separate persistent Xray `26.3.27` user service. It uses a
private VLESS/REALITY configuration at `~/.config/pdi-proxy/config.json`, mode
`600`, and exposes a mixed proxy only at `127.0.0.1:10808`. The service is
enabled, the user has lingering enabled, and the `codex` wrapper plus Git HTTPS
use this host-local proxy. It does not depend on the Mac remaining online.

Inspect without displaying credentials:

```bash
systemctl --user is-active pdi-xray.service
systemctl --user is-enabled pdi-xray.service
loginctl show-user harry -p Linger
ss -lnt | grep '127.0.0.1:10808'
```

The official macOS/Linux path is the standalone installer:

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
codex --version
```

Running the same installer updates Codex. If the host cannot reach the
installer or release CDN, stop rather than using an unverified mirror. A
GitHub release artifact is an acceptable fallback only after checking its
published digest and installing it into `~/.local/bin/codex`.

## Authentication

ChatGPT device-code authentication completed successfully on 2026-08-17.
`codex login status` reports `Logged in using ChatGPT`.

The host is headless, so authenticate with the device-code flow:

```bash
ssh -t harry@pdi-server
codex login --device-auth
codex login status
```

Open the printed URL on your own computer and enter the one-time code. Device
code login may first need to be enabled in ChatGPT security settings. Do not
send the code, token, or `~/.codex/auth.json` through Git, chat, or issue
trackers.

ChatGPT login uses subscription access. API-key login is a separate,
usage-billed option and is better suited to non-interactive automation:

```bash
printenv OPENAI_API_KEY | codex login --with-api-key
```

Do not store an API key in this repository or in a shell history entry.

## Development checkout

After the release commit is on GitHub:

```bash
mkdir -p ~/projects
git clone git@github.com:allentheboy01-sys/personal-ai-infrastructure.git \
  ~/projects/personal-ai-infrastructure
cd ~/projects/personal-ai-infrastructure
python3.13 -m venv .venv
.venv/bin/python -m pip install -e . pytest
.venv/bin/python -m pytest -q
codex
```

For database integration tests, set `PDI_TEST_DATABASE_URL` to the isolated
test database only. Never source `/etc/pdi/pdi.env` and never use production
database `pdi` as a test target.

GitHub SSH authentication is configured with a dedicated host key. The
development checkout uses the SSH remote and passed `git push --dry-run`; the
production checkout deliberately retains its HTTPS pull-only workflow.

## Workspace model

The long-term model is intentionally simple:

- a directory/Git repository is a Codex workspace;
- a Codex session is one chat within that workspace;
- `AGENTS.md` plus project documentation is authoritative durable context; and
- Codex Memory is an auxiliary recall layer, not a replacement for Git docs.

Ordinary projects do not require a registry or launcher. Create or enter a
directory and run `codex`. Launchers are only convenience commands for frequent
workspaces.

## Frequent workspace launchers

- `pdi-dev` → `/home/harry/projects/personal-ai-infrastructure`
- `ai-learning` → `/home/harry/projects/ai-learning`
- `feng-mbp` → `/home/harry/projects/ai-learning/projects/feng-mbp-time-series`
- `ai-learn` → legacy/deprecated compatibility name for `feng-mbp`

All launchers pass arguments unchanged to Codex. Therefore `resume --last`
resumes within the workspace selected by the launcher. AI launchers do not
read, print, move, or upload raw medical data.

## Chats, project context, and memory

These are three different layers:

| Layer | Authority | Host behavior |
|---|---|---|
| Project facts and rules | Git: `AGENTS.md`, architecture, context, release docs | Available in every clean checkout and every new chat |
| Chat transcript | Local Codex session state | New host chats can be resumed with `codex resume`; existing Mac-only chats are not assumed to migrate |
| Codex memory | Host-local generated files under `~/.codex/memories/` | Enabled on this host, separate from ChatGPT web memory |

Do not copy the entire Mac `~/.codex` directory to the server. It can contain
credentials, platform-specific config, plugins, absolute paths, sessions, and
generated state. Keep existing desktop chats where they are and start the
server workflow from the checked-in context:

```text
Read AGENTS.md, README.md, docs/context/CURRENT_CONTEXT.md, and the latest
release notes. Then inspect git status and summarize the next safe task.
```

Local Codex memory is enabled on this host:

```toml
# ~/.codex/config.toml
[features]
memories = true
```

Use `/memories` inside a chat to control whether that chat may read memories or
contribute to future memories. Required project rules remain in Git; memory is
only a recall layer.

## Daily workflow

```bash
ssh -t harry@pdi-server
pdi-dev
```

`pdi-dev` enters the development checkout, fetches `origin/main`, performs a
fast-forward only when the worktree is clean, and starts Codex. If local
changes exist, it preserves them, skips the automatic merge, prints status,
and still starts Codex for review.

Use `pdi-dev resume --last` to reopen the latest host-local PDI chat. Before
publishing, run the repository tests, review the diff, update current
context/release documents when behavior changed, and keep `/srv/projects/PDI`
untouched until the commit is reviewed and pushed.

Architecture and product discussion remains human-led with ChatGPT. PDI
implementation, tests, and Git run in the server development checkout. The Mac
is a client for SSH and optional review; it is no longer the primary PDI Codex
development environment. Existing Mac repositories and history are retained.

## Production promotion

Development completion does not automatically deploy production. Promote only
from a clean, reviewed `origin/main` using the fast-forward procedure in
`docs/deployment/server-runtime-v0.1.md`, then synchronize dependencies and
run the documented smoke checks. Never develop directly in `/srv/projects/PDI`.
