# Public release process

PDI uses one version authority for public releases:

1. `pyproject.toml` declares the exact package version `X.Y.Z`;
2. the public release note declares the same `vX.Y.Z` and is marked as a
   candidate until release approval;
3. a reviewed Release Gate creates Git tag `vX.Y.Z` on that exact commit; and
4. only after the tag exists may a GitHub Release or package publication call
   the version released.

An engineering milestone, branch, or untagged commit is not a public release.
This repository uses versioned release notes rather than a separate CHANGELOG;
historical engineering chronology belongs in `docs/archive/`.

## Candidate checklist

- update package version, public status, roadmap, and release note together;
- run host-safe, isolated PostgreSQL 16, clean-install, distribution, Markdown,
  portability, and current/history secret checks;
- confirm no production data, Provider credentials, or host-specific values
  entered the diff;
- record the candidate commit and obtain human review; and
- create no tag, GitHub Release, repository rename, or PyPI publication before
  that review.

The current supported installation model is a source checkout or source
distribution. The wheel provides the `pdi` CLI and MCP runtime, but it does not
carry the top-level Alembic migration tree; standalone wheel migration support
must not be claimed until that boundary is deliberately changed and tested.
