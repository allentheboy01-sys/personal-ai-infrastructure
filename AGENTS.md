# PDI repository guidance

## Project identity

- PDI is provider-independent Personal Digital Infrastructure.
- Providers enter through Adapters. Consumers use stable Query, Retrieval,
  Resource Access, or MCP boundaries.
- Jarvis and other AI runtimes are optional, replaceable consumers. PDI Core
  must not depend on a particular model, agent, or consumer runtime.
- Preserve the write, observation, read/retrieval, and resource-access
  boundaries documented in `ARCHITECTURE.md`.
- Consumers must not reach into SQLAlchemy, sessions, engines, ORM models,
  concrete repositories, or Provider credentials.
- Architecture or public-contract changes require matching architecture,
  design, or context documentation in the same change.

## Development workflow

- Use Python 3.13 and a repository-local virtual environment.
- Run `.venv/bin/python -m pytest -q` after Python or deployment changes.
- Integration tests require an explicit, isolated `PDI_TEST_DATABASE_URL`.
  Never point tests at a production database or load production environment
  files into a test process.
- Preserve unrelated work. Stop on an unexpectedly dirty worktree or history
  divergence; never reset or overwrite changes you do not own.
- Keep generated caches, credentials, local agent state, populated environment
  files, and Provider data out of Git.
- Before a release, update the public status, roadmap, and matching release
  notes without copying private operational state into the repository.

## Production safety

- Development and production checkouts must be separate. A production checkout
  is a deployment target, never a development worktree or test target.
- Production updates must be clean and fast-forward-only. Never reset, rebase,
  force-checkout, or run tests against production data on a runtime host.
- Never print or copy deployment environment files, authentication state,
  Provider/API credentials, or private personal data into logs, prompts,
  fixtures, screenshots, or reports.
- Hostnames, usernames, filesystem locations, ports, and network topology in
  public examples must be parameterized unless they are clearly synthetic.

See `docs/development/local-development.md` for the public development setup and
`SECURITY.md` for vulnerability and private-data handling guidance.
