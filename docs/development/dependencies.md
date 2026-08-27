# Dependency reproducibility

PDI uses two complementary dependency authorities:

- `pyproject.toml` declares direct dependencies and supported version ranges;
- `constraints/python3.13.txt` records the exact Python 3.13 dependency set
  validated by contributors and CI.

The constraints file is not an alternative project manifest. Add or remove a
direct dependency in `pyproject.toml`, then deliberately refresh and review the
constraint snapshot. Public self-host installs may use the supported ranges;
using the constraints reproduces the versions tested for the release
candidate.

## Install the reviewed set

From a clean Python 3.13 virtual environment:

```bash
PIP_CONSTRAINT="$(pwd)/constraints/python3.13.txt" \
  python -m pip install -e '.[test]'
python -m pip check
```

The monorepo host-safe suite also exercises the optional Jarvis reference
consumer. Its CI job explicitly installs the separate project under
`deployment/jarvis/web/python`; Jarvis and its dependencies are not included in
the PDI distribution or PDI Core runtime dependencies.

## Refresh intentionally

1. Create a new, empty Python 3.13 virtual environment outside the repository.
2. Install the project non-editably with `.[test]` and `build`, then install the
   separate Jarvis project only when refreshing the full monorepo test set.
3. Run `python -m pip check`.
4. Generate `python -m pip freeze`, remove the local `pdi @ file://...` line,
   and replace the constraint entries without adding editable or host paths.
5. Review every dependency change, then run the host-safe, isolated
   PostgreSQL, clean-install, and distribution checks.

Do not generate this file from a long-lived development environment. Dependency
updates are maintainer-reviewed changes; no automatic dependency bot is part of
the current release process.
