import hashlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def test_web_package_import_does_not_eagerly_load_legacy_pdi_facade() -> None:
    package = (ROOT / "src/jarvis/__init__.py").read_text(encoding="utf-8")
    preamble = package.split("def __getattr__", 1)[0]
    assert "from .application import" not in preamble


def test_systemd_unit_freezes_single_local_worker_and_hardening() -> None:
    unit = (ROOT / "deployment/systemd/jarvis-web.service").read_text(encoding="utf-8")
    required = (
        "User=harry", "Group=harry", "--host 127.0.0.1", "--port 8765", "--workers 1",
        "--no-access-log", "--no-proxy-headers", "KillMode=control-group", "UMask=0077",
        "PrivateTmp=yes", "ProtectSystem=strict", "ProtectHome=read-only",
        "-/run/docker.sock", "-/home/harry/.ssh", "-/home/harry/.codex", "-/home/harry/projects",
    )
    assert all(value in unit for value in required)
    assert "alembic" not in unit.lower()
    assert "0.0.0.0" not in unit


def test_hermes_launcher_has_a_sanitized_secret_boundary() -> None:
    launcher = (ROOT / "deployment/jarvis/web/hermes-bridge").read_text(encoding="utf-8")
    assert "exec env -i" in launcher
    assert "DEEPSEEK_API_KEY" in launcher
    assert "HERMES_HOME=/home/harry/.hermes/profiles/pdi-server" not in launcher  # assigned via quoted variable
    assert "JARVIS_DATABASE_URL" not in launcher
    assert "DATABASE__URL" not in launcher
    assert "pdi.env" not in launcher
    assert "/home/harry/.local/bin/jarvis" not in launcher


def test_release_verifier_accepts_complete_fixture_and_rejects_tamper(tmp_path: Path) -> None:
    sha = "a" * 40
    release = tmp_path / sha
    for directory in ("app", "static", "hermes", "bin", "manifests", "migrations"):
        (release / directory).mkdir(parents=True)
    wheel = release / "app/jarvis_web_app-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    (release / "static/index.html").write_text("index", encoding="utf-8")
    (release / "hermes/hermes_bridge.py").write_text("bridge", encoding="utf-8")
    (release / "bin/hermes-bridge").write_text("launcher", encoding="utf-8")
    lock = release / "manifests/requirements-production.lock"
    lock.write_text("locked", encoding="utf-8")
    (release / "migrations/jarvis-alembic.ini").write_text("migration", encoding="utf-8")
    info = release / "manifests/BUILD_INFO"
    info.write_text(f"GIT_SHA={sha}\nPYTHON_LOCK_SHA256={_digest(lock)}\nAPPLICATION_WHEEL_SHA256={_digest(wheel)}\n", encoding="utf-8")
    files = sorted(path for path in release.rglob("*") if path.is_file())
    sums = release / "manifests/SHA256SUMS"
    sums.write_text("".join(f"{_digest(path)}  {path.relative_to(release)}\n" for path in files), encoding="utf-8")
    verifier = ROOT / "deployment/jarvis/web/verify_release.py"
    subprocess.run([sys.executable, verifier, release, "--deploy-sha", sha], check=True, capture_output=True, text=True)
    wheel.write_bytes(b"tampered")
    failed = subprocess.run([sys.executable, verifier, release, "--deploy-sha", sha], capture_output=True, text=True)
    assert failed.returncode != 0
