# Local development

This guide describes a host-neutral development setup. It does not require a
particular server, username, VPN, proxy, AI runtime, or production layout.

## Prerequisites

- Git
- Python 3.13
- PostgreSQL only when running database integration tests

## Clone and create an environment

Choose a development directory you own:

```bash
git clone <repository-url> pdi
cd pdi
python3.13 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e . pytest
```

`<repository-url>` is the HTTPS or SSH clone URL selected by the contributor.
Do not substitute a production checkout for this development directory.

## Host-safe tests

Run the default suite from the repository root:

```bash
.venv/bin/python -m pytest -q
```

Tests that require a live Provider, external service, or database are skipped
unless their explicit test configuration is present. Do not load production
credentials to make skipped tests run.

## Isolated PostgreSQL integration tests

Database integration tests require `PDI_TEST_DATABASE_URL` and reject unsafe
database names. Create a disposable PostgreSQL database dedicated to tests,
then pass only that test URL to the command that needs it.

```bash
PDI_TEST_DATABASE_URL='<isolated-test-database-url>' \
  .venv/bin/python -m pytest -q tests/integration/database
```

The URL is a placeholder for a PostgreSQL database whose name ends in `_test`.
Never reuse a production database, role, or environment file. Migration
development is documented in
`docs/database-migrations.md`.

## Configuration safety

- `.env.example` documents configuration keys; never commit a populated `.env`.
- Use synthetic Provider accounts and data for integration development.
- Keep local credentials, generated caches, agent state, and test artifacts out
  of Git.
- Follow `SECURITY.md` when reporting a failure that may involve personal data.

## Git workflow

1. Start from a clean development worktree synchronized with the intended base.
2. Make the smallest coherent change and preserve unrelated work.
3. Run tests proportional to the change and `git diff --check`.
4. Review the complete diff for credentials, private data, generated files, and
   accidental deployment-specific assumptions.
5. Use a conventional, descriptive commit and push without rewriting shared
   history.

Repository-wide contributor and automation rules live in `AGENTS.md`.

## Production separation

A production checkout is a deployment target, not a development worktree. Do
not edit it directly, run tests against its database, source its environment
files, or use it to prepare commits. Production promotion and rollback must use
the deployment's reviewed, fast-forward-only procedure.
