# Contributing to PDI

PDI is provider-independent Personal Digital Infrastructure. Jarvis is an
optional reference consumer, not PDI Core. Before changing the repository,
read [`AGENTS.md`](AGENTS.md) for the rules shared by contributors and
automation.

## Development setup

Use Python 3.13 and a repository-local virtual environment:

```bash
git clone <your-fork-url> pdi
cd pdi
python3.13 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install \
  -c constraints/python3.13.txt -e '.[test]'
.venv/bin/python -m pytest -q
```

The default suite is host-safe. Database integration tests require a dedicated
PostgreSQL database whose name ends in `_test`:

```bash
PDI_TEST_DATABASE_URL='<isolated-postgresql-test-url>' \
  .venv/bin/python -m pytest -q tests/integration
```

Never use a production database, production Provider account, populated
environment file, or real personal data to run or create tests. See
[`docs/development/local-development.md`](docs/development/local-development.md)
for the complete isolation rules.

## Contribution flow

1. Fork the repository and create a focused branch.
2. Make the smallest coherent change.
3. Add deterministic tests and run the relevant host-safe and isolated
   PostgreSQL checks.
4. Update architecture, design, context, or public documentation when a
   contract changes.
5. Review the diff for credentials, private data, generated state, and
   deployment-specific assumptions, then open a focused pull request.

Provider integrations must normalize external state through the Adapter and
`ProviderFact` boundaries. They must not leak Provider-specific identity into
the World Model. Consumer integrations must use Query, Retrieval, Observation,
Resource Access, or MCP boundaries; they must not reach into PDI repositories,
ORM objects, sessions, engines, databases, or Provider credentials.

Pull requests should explain the problem and scope, list exact validation, and
call out any architecture or security implications. PDI does not require a
particular server, network overlay, container runtime, AI coding tool, or
consumer runtime for contributions.
