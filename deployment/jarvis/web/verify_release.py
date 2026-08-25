#!/usr/bin/env python3
"""Fail closed when a Jarvis release does not match its manifest."""

from __future__ import annotations

import argparse
import hashlib
import re
import stat
from pathlib import Path


SHA = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN = {"node_modules", ".git", "review", "screenshots", "test-results", "playwright-report"}
APPROVED_EXECUTABLES = {Path("bin/hermes-bridge"), Path("bin/jarvis-exec-proxy"), Path("bin/jarvis-web-access-proxy")}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("release", type=Path)
    parser.add_argument("--deploy-sha", required=True)
    args = parser.parse_args()
    root = args.release.resolve()
    if not SHA.fullmatch(args.deploy_sha) or root.name != args.deploy_sha:
        raise SystemExit("release path does not match DEPLOY_SHA")
    if any(part in FORBIDDEN for path in root.rglob("*") for part in path.relative_to(root).parts):
        raise SystemExit("release contains a forbidden generated/review path")
    if any(path.is_symlink() for path in root.rglob("*")):
        raise SystemExit("release must not contain symlinks")

    paths = (root, *root.rglob("*"))
    for path in paths:
        relative = path.relative_to(root)
        mode = stat.S_IMODE(path.stat().st_mode)
        expected = 0o555 if path.is_dir() or relative in APPROVED_EXECUTABLES else 0o444
        if mode != expected:
            raise SystemExit(f"release mode mismatch: {relative or Path('.')} expected {expected:o}")

    info = dict(line.split("=", 1) for line in (root / "manifests/BUILD_INFO").read_text().splitlines() if "=" in line)
    if info.get("GIT_SHA") != args.deploy_sha:
        raise SystemExit("BUILD_INFO Git SHA mismatch")
    wheels = tuple((root / "app").glob("*.whl"))
    if len(wheels) != 1 or digest(wheels[0]) != info.get("APPLICATION_WHEEL_SHA256"):
        raise SystemExit("application wheel mismatch")
    wheel = wheels[0]
    lock = root / "manifests/requirements-production.lock"
    if digest(lock) != info.get("PYTHON_LOCK_SHA256"):
        raise SystemExit("Python lock mismatch")

    listed: set[Path] = set()
    for line in (root / "manifests/SHA256SUMS").read_text().splitlines():
        expected, relative = line.split("  ", 1)
        path = root / relative
        if not path.is_file() or digest(path) != expected:
            raise SystemExit(f"artifact checksum mismatch: {relative}")
        listed.add(path.resolve())
    actual = {path.resolve() for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS"}
    if listed != actual:
        raise SystemExit("manifest file set mismatch")
    if not all(path.is_file() for path in (
        root / "static/index.html",
        root / "hermes/hermes_bridge.py",
        root / "migrations/jarvis-alembic.ini",
        root / "bin/jarvis-exec-proxy",
        root / "bin/jarvis-web-access-proxy",
        root / "profile/jarvis-web/config.yaml",
        root / "profile/jarvis-web/SOUL.md",
    )):
        raise SystemExit("required release component missing")
    if not all(path.is_dir() for path in (
        root / "profile/jarvis-web/cron",
        root / "profile/jarvis-web/sessions",
        root / "profile/jarvis-web/logs",
        root / "profile/jarvis-web/memories",
    )):
        raise SystemExit("required Hermes profile directory missing")
    print(f"verified {args.deploy_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
