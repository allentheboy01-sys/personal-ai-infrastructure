from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_postgres_reference_is_versioned_persistent_and_loopback_only() -> None:
    compose = (
        ROOT / "deployment/examples/postgres/compose.yaml"
    ).read_text()

    assert "image: postgres:16" in compose
    assert "pdi-postgres-data:/var/lib/postgresql/data" in compose
    assert "POSTGRES_PASSWORD:?" in compose
    assert "127.0.0.1" in compose
    assert "0.0.0.0" not in compose


def test_public_pdi_units_use_the_generic_reference_layout() -> None:
    services = tuple((ROOT / "deployment/systemd").glob("pdi-*.service"))

    assert services
    for path in services:
        service = path.read_text()
        assert "User=pdi" in service
        assert "Group=pdi" in service
        assert "WorkingDirectory=/opt/pdi" in service
        assert "harry" not in service.lower()
        assert "/srv/projects/PDI" not in service


def test_primary_runtime_and_deployment_paths_have_no_author_literals() -> None:
    roots = (
        ROOT / "src/pdi",
        ROOT / "src/pdi_mcp",
        ROOT / "src/pdi_resource_access",
        ROOT / "deployment",
    )
    files = [
        path
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
        and "requirements-production.lock" not in path.name
    ]
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in files
    )

    for literal in (
        "harry",
        "/home/harry",
        "/srv/projects/PDI",
        "pdi-server",
        "tailfdc57b.ts.net",
    ):
        assert literal.lower() not in text.lower()


def test_root_environment_example_is_pdi_only() -> None:
    example = (ROOT / ".env.example").read_text()

    assert "DATABASE__URL=" in example
    assert "NEXTCLOUD__URL=" in example
    assert "IMMICH__URL=" in example
    assert "GMAIL__TOKEN_FILE=" in example
    assert "OPENROUTER_API_KEY" not in example
    assert "OPENAI_API_KEY" not in example
