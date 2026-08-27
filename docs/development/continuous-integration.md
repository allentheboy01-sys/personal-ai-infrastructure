# Continuous integration

GitHub Actions validates PDI without production credentials or live Providers.
The workflows use `permissions: contents: read` and synthetic PostgreSQL
credentials only.

## Jobs

- **Host safe** installs PDI plus test dependencies under Python 3.13, runs
  `pip check`, the default host-safe suite, documentation links, and public
  portability checks. Optional Jarvis reference-consumer dependencies are
  installed only for the monorepo compatibility tests; they are not PDI Core
  dependencies.
- **PostgreSQL 16** creates an isolated database whose name ends in `_test`,
  applies Alembic from empty state, and runs the existing database-backed
  repository, Query, Retrieval, Observation, Resource Access, and MCP tests.
- **Package and clean install** builds an sdist and wheel, checks their declared
  boundary, installs the wheel into a new virtual environment, and exercises
  the public CLI. The source distribution includes Alembic assets; standalone
  wheel migrations are not currently supported.
- **Secret scan** checks current content and reachable Git history with
  Gitleaks. Checkout uses full history, output is redacted, and exceptions are
  narrowly documented in `.gitleaks.toml`.

No job contacts Nextcloud, Immich, Gmail, or another live Provider. Browser
production E2E and large Provider scans are outside public PDI CI.

## Action pinning policy

Official GitHub actions are pinned to reviewed full commit SHAs and annotated
with their supported major release. Third-party actions are always pinned by
full commit SHA. Current reviewed actions are:

| Action | Pin | Purpose |
| --- | --- | --- |
| `actions/checkout` | `d23441a48e516b6c34aea4fa41551a30e30af803` | source checkout, v6 |
| `actions/setup-python` | `ece7cb06caefa5fff74198d8649806c4678c61a1` | Python setup, v6 |
| `gitleaks/gitleaks-action` | `e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e` | current/history secret scan, v3 |

Action upgrades are deliberate dependency changes: verify the upstream release
and commit, update this table and workflows together, then review the complete
workflow diff.
