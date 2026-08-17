# PDI repository guidance

## Project boundaries

- PDI is the provider-independent infrastructure. Jarvis and other AI runtimes
  are replaceable consumers.
- Preserve the write, observation, read/retrieval, and resource-access
  boundaries documented in `ARCHITECTURE.md`.
- Consumers use public application services or MCP. They must not reach into
  SQLAlchemy, sessions, engines, ORM models, or provider credentials.
- Architecture or public-contract changes require the matching design/context
  documentation in the same change.

## Development workflow

- Use Python 3.13 and the repository virtual environment.
- Run `.venv/bin/python -m pytest -q` after Python or deployment changes.
- Integration tests require an explicit isolated `PDI_TEST_DATABASE_URL`.
  Never point tests at the production `pdi` database or source `/etc/pdi/pdi.env`
  into a test process.
- Keep generated caches, credentials, local Codex state, and environment files
  out of Git.
- Before a release, update `README.md`, `docs/context/CURRENT_CONTEXT.md`, the
  roadmap, and the matching file under `docs/releases/`.

## Host safety

- `/srv/projects/PDI` is the production checkout on `pdi-server`; do not use it
  as a development worktree.
- Develop in the separate user-owned checkout documented in
  `docs/development/codex-cli-on-pdi-server.md`.
- Production updates are clean, fast-forward-only pulls. Never reset, rebase,
  force-checkout, or run pytest against production data on the runtime host.
- Never print or copy the contents of `/etc/pdi/*.env`, `~/.codex/auth.json`, or
  provider/API credentials.
