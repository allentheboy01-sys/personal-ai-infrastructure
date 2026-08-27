#!/usr/bin/env python3
"""Check the documented source-distribution and wheel release boundaries."""

from __future__ import annotations

from pathlib import Path
import sys
import tarfile
import zipfile


def one_match(directory: Path, pattern: str) -> Path:
    matches = tuple(directory.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one {pattern} artifact, found {len(matches)}"
        )
    return matches[0]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: check_distribution.py DIST_DIRECTORY", file=sys.stderr)
        return 2

    directory = Path(args[0])
    sdist = one_match(directory, "*.tar.gz")
    wheel = one_match(directory, "*.whl")

    with tarfile.open(sdist, "r:gz") as archive:
        names = set(archive.getnames())
    prefix = next(name.split("/", 1)[0] for name in names)
    required_sdist = {
        f"{prefix}/.env.example",
        f"{prefix}/alembic.ini",
        f"{prefix}/constraints/python3.13.txt",
        f"{prefix}/migrations/env.py",
        f"{prefix}/README.md",
        f"{prefix}/LICENSE",
    }
    missing_sdist = required_sdist - names
    if missing_sdist:
        raise RuntimeError(
            "sdist is missing: " + ", ".join(sorted(missing_sdist))
        )
    if not any(name.startswith(f"{prefix}/migrations/versions/") for name in names):
        raise RuntimeError("sdist contains no Alembic migration revisions")
    if any(name.startswith(f"{prefix}/src/jarvis/") for name in names):
        raise RuntimeError("PDI sdist must not package the Jarvis consumer")

    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())
    required_wheel_suffixes = {
        "pdi/cli.py",
        "pdi_mcp/bootstrap.py",
    }
    for suffix in required_wheel_suffixes:
        if not any(name.endswith(suffix) for name in wheel_names):
            raise RuntimeError(f"wheel is missing {suffix}")
    entry_points = next(
        (name for name in wheel_names if name.endswith(".dist-info/entry_points.txt")),
        None,
    )
    if entry_points is None:
        raise RuntimeError("wheel is missing console entry-point metadata")
    if any(name.startswith("jarvis/") for name in wheel_names):
        raise RuntimeError("PDI wheel must not package the Jarvis consumer")

    print(f"sdist boundary verified: {sdist.name}")
    print(f"wheel boundary verified: {wheel.name}")
    print("Alembic migrations are supported from the source distribution only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
