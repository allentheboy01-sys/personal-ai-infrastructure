#!/usr/bin/env python3
"""Build an immutable Jarvis Web release from one clean Git commit."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LOCK = ROOT / "deployment/jarvis/web/requirements-production.lock"
FRONTEND = ROOT / "apps/jarvis-web"
PYTHON_ARTIFACT = ROOT / "deployment/jarvis/web/python"
APPROVED_EXECUTABLES = {Path("bin/hermes-bridge"), Path("bin/jarvis-exec-proxy")}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def run(*command: str, cwd: Path = ROOT) -> str:
    return subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


def normalize_release_modes(root: Path) -> None:
    """Make executable intent and immutable readability deterministic."""

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_dir():
            os.chmod(path, 0o555)
        elif path.is_file():
            os.chmod(path, 0o555 if relative in APPROVED_EXECUTABLES else 0o444)
    os.chmod(root, 0o555)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deploy-sha", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    sha = run("git", "rev-parse", "HEAD")
    if args.deploy_sha != sha or len(sha) != 40:
        raise SystemExit("DEPLOY_SHA does not equal the checked-out commit")
    if run("git", "status", "--porcelain"):
        raise SystemExit("release builds require a clean worktree")
    release = args.output_root.resolve() / sha
    if release.exists():
        raise SystemExit("release directory already exists")

    staging = args.output_root.resolve() / f".{sha}.staging-{os.getpid()}"
    try:
        for directory in (
            "app",
            "static",
            "hermes",
            "bin",
            "manifests",
            "migrations",
            "profile/jarvis-web/cron",
            "profile/jarvis-web/sessions",
            "profile/jarvis-web/logs",
            "profile/jarvis-web/memories",
        ):
            (staging / directory).mkdir(parents=True, exist_ok=True)
        python_build = staging / ".python-build"
        shutil.copytree(ROOT / "src/jarvis", python_build / "src/jarvis", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        artifact_config = (PYTHON_ARTIFACT / "pyproject.toml").read_text(encoding="utf-8")
        (python_build / "pyproject.toml").write_text(
            artifact_config.replace('where = ["../../../../src"]', 'where = ["src"]'),
            encoding="utf-8",
        )
        run(
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(staging / "app"),
            ".",
            cwd=python_build,
        )
        shutil.rmtree(python_build)
        run("npm", "ci", cwd=FRONTEND)
        run("npm", "run", "build", cwd=FRONTEND)
        shutil.copytree(FRONTEND / "dist", staging / "static", dirs_exist_ok=True)
        shutil.copy2(ROOT / "src/jarvis/runtime/hermes_bridge.py", staging / "hermes/hermes_bridge.py")
        shutil.copy2(ROOT / "deployment/jarvis/web/hermes-bridge", staging / "bin/hermes-bridge")
        shutil.copy2(ROOT / "deployment/jarvis/web/jarvis-exec-proxy", staging / "bin/jarvis-exec-proxy")
        shutil.copy2(ROOT / "deployment/jarvis/web/profile/config.yaml", staging / "profile/jarvis-web/config.yaml")
        shutil.copy2(ROOT / "deployment/jarvis/web/profile/SOUL.md", staging / "profile/jarvis-web/SOUL.md")
        shutil.copy2(LOCK, staging / "manifests/requirements-production.lock")
        shutil.copy2(ROOT / "jarvis-alembic.ini", staging / "migrations/jarvis-alembic.ini")
        shutil.copytree(ROOT / "jarvis_migrations", staging / "migrations/jarvis_migrations", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        wheels = tuple((staging / "app").glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("release must contain exactly one application wheel")
        wheel = wheels[0]
        build_info = "\n".join(
            (
                f"GIT_SHA={sha}",
                f"BUILD_TIMESTAMP={datetime.now(UTC).replace(microsecond=0).isoformat()}",
                f"FRONTEND_LOCK_SHA256={digest(FRONTEND / 'package-lock.json')}",
                f"PYTHON_LOCK_SHA256={digest(LOCK)}",
                f"APPLICATION_WHEEL_SHA256={digest(wheel)}",
                "",
            )
        )
        (staging / "manifests/BUILD_INFO").write_text(build_info, encoding="utf-8")
        files = sorted(path for path in staging.rglob("*") if path.is_file())
        sums = "".join(f"{digest(path)}  {path.relative_to(staging)}\n" for path in files)
        (staging / "manifests/SHA256SUMS").write_text(sums, encoding="utf-8")
        normalize_release_modes(staging)
        staging.rename(release)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(release)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
