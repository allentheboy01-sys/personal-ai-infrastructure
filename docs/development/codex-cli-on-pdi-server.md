# Codex CLI on `pdi-server`

## Decision

Primary PDI development may run on `pdi-server`, close to the real Linux
runtime and isolated PostgreSQL test infrastructure. Development must use a
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

The official macOS/Linux path is the standalone installer:

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
codex --version
```

Running the same installer updates Codex. If the host cannot reach the
installer or release CDN, stop rather than using an unverified mirror. A
GitHub release artifact is an acceptable fallback only after checking its
published digest and installing it into `~/.local/bin/codex`.

## One human authentication step

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
git clone https://github.com/allentheboy01-sys/personal-ai-infrastructure.git \
  ~/projects/personal-ai-infrastructure
cd ~/projects/personal-ai-infrastructure
python3.13 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m pytest -q
codex
```

For database integration tests, set `PDI_TEST_DATABASE_URL` to the isolated
test database only. Never source `/etc/pdi/pdi.env` and never use production
database `pdi` as a test target.

## Chats, project context, and memory

These are three different layers:

| Layer | Authority | Host behavior |
|---|---|---|
| Project facts and rules | Git: `AGENTS.md`, architecture, context, release docs | Available in every clean checkout and every new chat |
| Chat transcript | Local Codex session state | New host chats can be resumed with `codex resume`; existing Mac-only chats are not assumed to migrate |
| Codex memory | Host-local generated files under `~/.codex/memories/` | Optional, separate from ChatGPT web memory, and off by default |

Do not copy the entire Mac `~/.codex` directory to the server. It can contain
credentials, platform-specific config, plugins, absolute paths, sessions, and
generated state. Keep existing desktop chats where they are and start the
server workflow from the checked-in context:

```text
Read AGENTS.md, README.md, docs/context/CURRENT_CONTEXT.md, and the latest
release notes. Then inspect git status and summarize the next safe task.
```

Enable local Codex memory only if you want host chats to contribute to future
host chats:

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
cd ~/projects/personal-ai-infrastructure
git status --short --branch
git pull --ff-only
codex
```

Use `codex resume` to reopen a host-local chat. Before publishing, run the
repository tests, review the diff, update current context/release documents
when behavior changed, and keep `/srv/projects/PDI` untouched until the commit
is reviewed and pushed.

## Production promotion

Development completion does not automatically deploy production. Promote only
from a clean, reviewed `origin/main` using the fast-forward procedure in
`docs/deployment/server-runtime-v0.1.md`, then synchronize dependencies and
run the documented smoke checks. Never develop directly in `/srv/projects/PDI`.
