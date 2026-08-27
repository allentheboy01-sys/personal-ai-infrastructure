# Clean-clone portability acceptance

Use this bounded runbook before a public release to verify that installation
does not rely on the maintainer's workstation or production deployment. Run it
in a temporary directory with synthetic configuration only.

## Required checks

1. Clone the candidate commit into a fresh temporary checkout.
2. Create a Python 3.13 virtual environment and run `pip install -e .`.
3. Verify `pip check`, `pdi --help`, and `pdi sync --help`.
4. Verify `alembic -c alembic.ini heads` resolves the packaged migration tree.
5. With a synthetic database URL and no Provider variables, verify the MCP
   composition starts over stdio and exits cleanly at end-of-input.
6. Construct Nextcloud-only and Immich-only sync composition with synthetic
   settings without opening Provider connections.
7. Verify an implicit sync with no eligible Provider fails clearly and that
   Gmail is never selected implicitly.
8. Search primary runtime, configuration, and deployment paths for maintainer
   usernames, hostnames, home directories, and production checkout paths.

An isolated PostgreSQL integration run may additionally apply migrations and
exercise MCP requests. It must use an explicit test database and must never load
production configuration or Provider accounts.

## Acceptance boundary

This is an installation and composition check, not a Provider qualification or
load test. It must not contact real Providers, modify production services,
install tracked systemd units, or use personal data. Preserve the temporary
checkout only long enough to diagnose a failure.
