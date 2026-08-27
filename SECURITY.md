# Security policy

PDI handles credentials and personal data from external Providers. Security
reports must therefore minimize further disclosure.

## Reporting a vulnerability

Do not open a public issue containing credentials, private data, exploit
details, screenshots of personal content, or live infrastructure identifiers.

If the repository host offers private vulnerability reporting, use that
channel. Otherwise, contact a maintainer through an already established private
channel. If no private channel is available, open a minimal public issue asking
the maintainers to establish one; include no sensitive technical details.

This project does not currently promise a response SLA. Reports should contain
only the information needed to reproduce and assess the issue safely.

## Credential handling

- Never commit Provider credentials, database passwords, API keys, OAuth
  tokens, cookies, populated environment files, or authentication state.
- Do not print credentials or secret-bearing configuration objects in logs,
  exceptions, test output, screenshots, prompts, or reports.
- Examples and tests must use explicit synthetic values.
- If a real credential is accidentally published, rotate or revoke it first.
  Consider history rewriting only after containment and a separate review.

## Data and test isolation

- Never run tests against a production PDI database or real Provider account.
- Database integration tests require an explicit isolated test database.
- Do not add personal documents, Provider responses, production database dumps,
  private filenames, faces, conversations, email content, or content-derived
  fingerprints as fixtures or review artifacts.
- Prefer minimal, synthetic fixtures that demonstrate the contract without
  representing a real person's data.

## Trust boundaries

- Consumers use PDI's public application services, MCP, or Resource Access.
  They must not bypass those boundaries to access ORM objects, sessions,
  engines, concrete repositories, databases, or Provider credentials.
- Resource Access must return only approved, bounded representations and must
  not expose Provider credentials or internal filesystem paths.
- Provider data is external input. Adapters validate and normalize it before
  PDI Core uses it.

See `docs/security/private-operations-boundary.md` for the separation between
public project material and private deployment operations.
