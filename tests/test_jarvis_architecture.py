import ast
import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_jarvis_never_imports_pdi_persistence_internals() -> None:
    forbidden = ("pdi.database", "pdi.repository", "pdi.repository.orm")
    violations = []
    for path in (ROOT / "src/jarvis").rglob("*.py"):
        for imported in _imports(path):
            if imported == forbidden[0] or imported.startswith(forbidden[1]):
                violations.append(f"{path.relative_to(ROOT)}: {imported}")
    assert violations == []


def test_pdi_never_imports_jarvis() -> None:
    violations = [str(path.relative_to(ROOT)) for package in ("pdi", "pdi_mcp") for path in (ROOT / f"src/{package}").rglob("*.py") if any(name == "jarvis" or name.startswith("jarvis.") for name in _imports(path))]
    assert violations == []


def test_runtime_contract_is_framework_and_hermes_independent() -> None:
    imports = _imports(ROOT / "src/jarvis/runtime/contract.py")
    assert not any(name.startswith(("fastapi", "sqlalchemy", "hermes")) for name in imports)


def test_jarvis_state_never_imports_pdi() -> None:
    violations = [str(path.relative_to(ROOT)) for path in (ROOT / "src/jarvis/state").rglob("*.py") if any(name == "pdi" or name.startswith("pdi.") for name in _imports(path))]
    assert violations == []


def test_frontend_has_no_direct_service_or_secret_boundary() -> None:
    forbidden = ("gmail.googleapis", "/run/pdi", "postgresql://", "remote.php", "navigator.serviceWorker", "new WebSocket")
    violations = []
    for path in (ROOT / "apps/jarvis-web/src").rglob("*"):
        if path.is_file() and path.suffix in {".ts", ".tsx", ".css"}:
            text = path.read_text(encoding="utf-8")
            if any(token in text for token in forbidden):
                violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_runtime_implementation_is_not_a_browser_contract() -> None:
    from jarvis.web import create_app
    from jarvis.web.schemas import CreateConversationRequest, CreateTurnRequest

    assert inspect.signature(create_app).parameters["runtime"].default is inspect.Parameter.empty
    assert set(CreateConversationRequest.model_fields) == {"title"}
    assert set(CreateTurnRequest.model_fields) == {"body"}
    frontend = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "apps/jarvis-web/src").rglob("*.ts*"))
    assert "MockRuntimeAdapter" not in frontend
    assert "HermesRuntimeAdapter" not in frontend
