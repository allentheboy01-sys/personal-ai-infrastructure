import hashlib
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_fixture(release: Path) -> None:
    for path in release.rglob("*"):
        if path.is_dir():
            path.chmod(0o555)
        elif path.is_file():
            path.chmod(0o555 if path.relative_to(release) in {Path("bin/hermes-bridge"), Path("bin/jarvis-exec-proxy")} else 0o444)
    release.chmod(0o555)


def test_production_lock_is_exact_and_hashed() -> None:
    lock = (ROOT / "deployment/jarvis/web/requirements-production.lock").read_text(encoding="utf-8")
    requirements = [line for line in lock.splitlines() if line and not line.startswith(("#", "--", " "))]
    assert len(requirements) >= 40
    assert all("==" in line and line[-1] == "\\" for line in requirements)
    assert lock.count("--hash=sha256:") >= len(requirements)
    lines = lock.splitlines()
    positions = [index for index, line in enumerate(lines) if line in requirements]
    assert all(any("--hash=sha256:" in line for line in lines[start + 1 : (positions[index + 1] if index + 1 < len(positions) else len(lines))]) for index, start in enumerate(positions))
    assert not any(name in lock.lower() for name in ("hermes-agent", "pytest", "playwright", "redis", "celery", "google-api-python-client"))
    assert "google-auth==" not in lock.lower()
    assert "pypdf==" not in lock.lower()
    assert "# via pdi (" not in lock.lower()


def test_python_artifact_packages_only_jarvis() -> None:
    configuration = (ROOT / "deployment/jarvis/web/python/pyproject.toml").read_text(encoding="utf-8")
    assert 'include = ["jarvis", "jarvis.*"]' in configuration
    assert "google-auth" not in configuration
    assert "pypdf" not in configuration
    builder = (ROOT / "deployment/jarvis/web/build_release.py").read_text(encoding="utf-8")
    assert 'copytree(ROOT / "src/jarvis"' in builder
    assert 'shutil.rmtree(python_build)' in builder
    assert "normalize_release_modes(staging)" in builder


def test_web_package_import_does_not_eagerly_load_legacy_pdi_facade() -> None:
    package = (ROOT / "src/jarvis/__init__.py").read_text(encoding="utf-8")
    preamble = package.split("def __getattr__", 1)[0]
    assert "from .application import" not in preamble


def test_systemd_unit_freezes_single_local_worker_and_hardening() -> None:
    unit = (ROOT / "deployment/systemd/jarvis-web.service").read_text(encoding="utf-8")
    required = (
        "User=harry", "Group=harry", "--host 127.0.0.1", "--port 8765", "--workers 1",
        "--no-access-log", "--no-proxy-headers", "KillMode=mixed", "UMask=0077",
        "PrivateTmp=yes", "ProtectSystem=strict", "ProtectHome=read-only",
        "RuntimeDirectory=jarvis-web-hermes-sessions jarvis-web-hermes-logs",
        "RuntimeDirectoryMode=0700",
        "BindPaths=/run/jarvis-web-hermes-sessions:/opt/jarvis-web/current/profile/jarvis-web/sessions",
        "BindPaths=/run/jarvis-web-hermes-logs:/opt/jarvis-web/current/profile/jarvis-web/logs",
        "-/run/docker.sock", "-/home/harry/.ssh", "-/home/harry/.codex", "-/home/harry/projects",
    )
    assert all(value in unit for value in required)
    assert [line for line in unit.splitlines() if line.startswith("BindPaths=")] == [
        "BindPaths=/run/jarvis-web-hermes-sessions:/opt/jarvis-web/current/profile/jarvis-web/sessions",
        "BindPaths=/run/jarvis-web-hermes-logs:/opt/jarvis-web/current/profile/jarvis-web/logs",
    ]
    assert "alembic" not in unit.lower()
    assert "0.0.0.0" not in unit
    assert "ProtectHome=no" not in unit
    assert "ReadWritePaths=" not in unit
    assert "StateDirectory=" not in unit
    assert "BindPaths=/run/jarvis-web-hermes-sessions:/home/harry/.hermes\n" not in unit


def test_hermes_launcher_has_a_sanitized_secret_boundary() -> None:
    launcher = (ROOT / "deployment/jarvis/web/hermes-bridge").read_text(encoding="utf-8")
    assert "exec env -i" in launcher
    assert "DEEPSEEK_API_KEY" in launcher
    assert "HERMES_HOME=/home/harry/.hermes/profiles/pdi-server" not in launcher  # assigned via quoted variable
    assert "JARVIS_DATABASE_URL" not in launcher
    assert "DATABASE__URL" not in launcher
    assert "pdi.env" not in launcher
    assert "/home/harry/.local/bin/jarvis" not in launcher


def test_web_profile_has_complete_read_only_hermes_home_scaffold() -> None:
    builder = (ROOT / "deployment/jarvis/web/build_release.py").read_text(encoding="utf-8")
    for required in (
        "profile/jarvis-web/cron",
        "profile/jarvis-web/sessions",
        "profile/jarvis-web/logs",
        "profile/jarvis-web/memories",
    ):
        assert required in builder
    assert 'profile/jarvis-web/SOUL.md' in builder
    soul = (ROOT / "deployment/jarvis/web/profile/SOUL.md").read_text(
        encoding="utf-8"
    )
    soul_flat = " ".join(soul.split())
    for policy in (
        "prefer relation-backed `pdi_rich_retrieve_resources`",
        "bare or quoted name/label-like phrase",
        "Do not discover labels first merely to confirm an explicit label",
        "`pdi_aggregate_resources` with `group_by=person_label`",
        "at most one label-discovery call for the same user intent",
        "Never fabricate or blindly try alternate labels",
        "ask the user to clarify",
        "`filters.mime_category=image`",
        "`filters.mime_category=video`",
        "stop retrieval for that intent",
        "Do not substitute semantic results",
        "Do not invent a duration",
    ):
        assert policy in soul_flat
    for private_example in ("妈妈", "我妈", "母亲", "Mom"):
        assert private_example not in soul


def _release_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    sha = "a" * 40
    release = tmp_path / sha
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
        (release / directory).mkdir(parents=True)
    wheel = release / "app/jarvis_web_app-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    (release / "static/index.html").write_text("index", encoding="utf-8")
    (release / "hermes/hermes_bridge.py").write_text("bridge", encoding="utf-8")
    (release / "bin/hermes-bridge").write_text("launcher", encoding="utf-8")
    (release / "bin/jarvis-exec-proxy").write_text("proxy", encoding="utf-8")
    (release / "profile/jarvis-web/config.yaml").write_text("profile", encoding="utf-8")
    (release / "profile/jarvis-web/SOUL.md").write_text("", encoding="utf-8")
    lock = release / "manifests/requirements-production.lock"
    lock.write_text("locked", encoding="utf-8")
    (release / "migrations/jarvis-alembic.ini").write_text("migration", encoding="utf-8")
    info = release / "manifests/BUILD_INFO"
    info.write_text(f"GIT_SHA={sha}\nPYTHON_LOCK_SHA256={_digest(lock)}\nAPPLICATION_WHEEL_SHA256={_digest(wheel)}\n", encoding="utf-8")
    files = sorted(path for path in release.rglob("*") if path.is_file())
    sums = release / "manifests/SHA256SUMS"
    sums.write_text("".join(f"{_digest(path)}  {path.relative_to(release)}\n" for path in files), encoding="utf-8")
    _normalize_fixture(release)
    return release, wheel, sums


def _verify(release: Path) -> subprocess.CompletedProcess[str]:
    verifier = ROOT / "deployment/jarvis/web/verify_release.py"
    return subprocess.run([sys.executable, verifier, release, "--deploy-sha", release.name], capture_output=True, text=True)


def test_release_verifier_accepts_complete_fixture_and_rejects_tamper(tmp_path: Path) -> None:
    release, wheel, _ = _release_fixture(tmp_path)
    assert _verify(release).returncode == 0
    wheel.chmod(0o644)
    wheel.write_bytes(b"tampered")
    assert _verify(release).returncode != 0


def test_release_verifier_rejects_root_only_launcher(tmp_path: Path) -> None:
    release, _, _ = _release_fixture(tmp_path)
    (release / "bin/hermes-bridge").chmod(0o500)
    assert _verify(release).returncode != 0


def test_release_verifier_rejects_writable_payload(tmp_path: Path) -> None:
    release, _, _ = _release_fixture(tmp_path)
    (release / "static/index.html").chmod(0o644)
    assert _verify(release).returncode != 0


def test_release_verifier_rejects_unexpected_executable(tmp_path: Path) -> None:
    release, _, _ = _release_fixture(tmp_path)
    (release / "hermes/hermes_bridge.py").chmod(0o555)
    assert _verify(release).returncode != 0


def test_release_modes_are_readable_but_not_writable(tmp_path: Path) -> None:
    release, _, _ = _release_fixture(tmp_path)
    assert os.access(release / "static/index.html", os.R_OK)
    assert os.access(release / "bin/hermes-bridge", os.R_OK | os.X_OK)
    assert all(path.stat().st_mode & 0o222 == 0 for path in (release, *release.rglob("*")))
