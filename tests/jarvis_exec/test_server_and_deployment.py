import asyncio
from pathlib import Path

from jarvis.exec.contract import EXEC_TOOL_NAMES
from jarvis.exec.server import create_server
from jarvis.exec.workspace import Workspace


ROOT = Path(__file__).resolve().parents[2]


def test_server_exposes_exact_contract(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "workspace")
    try:
        server = create_server(workspace)
        tools = asyncio.run(server.list_tools())
        assert tuple(tool.name for tool in tools) == EXEC_TOOL_NAMES
    finally:
        workspace.close()


def test_web_profile_is_minimal_and_separate() -> None:
    text = (ROOT / "deployment/jarvis/web/profile/config.yaml").read_text()
    assert "toolsets: []" in text
    assert "  cli:\n    - pdi\n    - jarvis_exec\n    - jarvis_web\n" in text
    assert "memory_enabled: false" in text
    assert "user_profile_enabled: false" in text
    assert text.count("        - pdi_") == 7
    assert all(f"        - {name}" in text for name in EXEC_TOOL_NAMES)
    assert sum(text.count(f"        - {name}\n") for name in EXEC_TOOL_NAMES) == len(EXEC_TOOL_NAMES)
    for forbidden in ("terminal", "code_execution", "browser", "delegation"):
        assert forbidden not in text
    assert "        - web_search\n" not in text
    assert "        - web_extract\n" not in text


def test_exec_units_freeze_socket_and_sandbox() -> None:
    socket = (ROOT / "deployment/systemd/jarvis-exec.socket").read_text()
    service = (ROOT / "deployment/systemd/jarvis-exec@.service").read_text()
    for value in ("Accept=yes", "MaxConnections=4", "SocketMode=0660", "RemoveOnStop=yes"):
        assert value in socket
    assert "ListenStream=/run/jarvis-exec.sock" in socket
    assert "ListenStream=0.0.0.0" not in socket
    for value in (
        "DynamicUser=yes", "PrivateNetwork=yes", "RestrictAddressFamilies=AF_UNIX",
        "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "PrivateDevices=yes",
        "ProtectProc=invisible", "ProcSubset=pid", "KillMode=control-group",
        "StandardInput=socket", "StandardOutput=inherit", "StandardError=journal",
        "Environment=JARVIS_EXEC_WORKSPACE=/workspace/work",
        "TemporaryFileSystem=/workspace:rw,nodev,nosuid,noexec,size=16M,mode=1777",
        "InaccessiblePaths=/tmp /var/tmp -/dev/shm -/dev/mqueue -/dev/hugepages ",
        "MemoryMax=256M", "MemorySwapMax=0", "TasksMax=32", "RuntimeMaxSec=300s",
    ):
        assert value in service
    for path in (
        "/tmp", "/var/tmp", "/dev/shm", "/dev/mqueue", "/dev/hugepages",
        "/etc/pdi", "/etc/jarvis", "/home", "/srv/projects",
        "/run/docker.sock", "/var/run/docker.sock",
    ):
        assert path in service
    assert "EnvironmentFile=" not in service
    assert "RuntimeDirectory=" not in service
    assert "User=harry" not in service
    web = (ROOT / "deployment/systemd/jarvis-web.service").read_text()
    assert "Requires=pdi-resource-access.service jarvis-exec.socket" in web


def test_exec_packages_have_no_product_authority_imports() -> None:
    for directory in (ROOT / "src/jarvis/exec", ROOT / "src/jarvis/exec_proxy"):
        text = "\n".join(path.read_text() for path in directory.glob("*.py"))
        for forbidden in ("import pdi", "jarvis.state", "jarvis.web", "hermes"):
            assert forbidden not in text.lower()


def test_workspace_child_is_private(tmp_path: Path) -> None:
    root = tmp_path / "mount-root" / "work"
    workspace = Workspace(root)
    try:
        assert root.stat().st_mode & 0o777 == 0o700
    finally:
        workspace.close()


def test_proxy_launcher_is_secret_free() -> None:
    launcher = (ROOT / "deployment/jarvis/web/jarvis-exec-proxy").read_text()
    assert "exec env -i" in launcher
    for forbidden in ("DEEPSEEK", "JARVIS_DATABASE_URL", "pdi.env", "jarvis.env"):
        assert forbidden not in launcher


def test_production_profile_uses_only_stable_release_paths() -> None:
    profile = (ROOT / "deployment/jarvis/web/profile/config.yaml").read_text()
    assert "/opt/jarvis-web/current/bin/jarvis-exec-proxy" in profile
    assert "/run/jarvis-e5-1-validation" not in profile
