from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_public_package_metadata_and_release_authority_agree() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    project = pyproject["project"]

    assert project["name"] == "pdi"
    assert project["version"] == "0.6.0"
    assert project["requires-python"] == ">=3.13"
    assert project["license"] == "MIT"
    assert project["scripts"]["pdi"] == "pdi.cli:main"
    assert "jarvis-web" not in project["optional-dependencies"]
    assert set(project["urls"]) == {
        "Homepage",
        "Documentation",
        "Repository",
        "Issues",
    }
    assert all(
        "allentheboy01-sys/personal-digital-infrastructure" in url
        for url in project["urls"].values()
    )

    release = (ROOT / "docs/releases/v0.6.0.md").read_text()
    assert "Release authority" in release
    assert "annotated Git tag `v0.6.0`" in release
    assert "without that tag" in release
    assert "already released" not in release


def test_ci_has_least_privilege_and_required_jobs() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    assert "permissions:\n  contents: read" in workflow
    assert "host-safe:" in workflow
    assert "postgresql-integration:" in workflow
    assert "image: postgres:16" in workflow
    assert "package-clean-install:" in workflow
    assert "PDI_TEST_DATABASE_URL" in workflow
    assert "PDI_TEST_DATABASE_URL: ${{ secrets." not in workflow
    assert "NEXTCLOUD__PASSWORD" not in workflow
    assert "IMMICH__API_KEY" not in workflow


def test_secret_scan_is_full_history_pinned_and_narrowly_allowlisted() -> None:
    workflow = (ROOT / ".github/workflows/secret-scan.yml").read_text()
    config = (ROOT / ".gitleaks.toml").read_text()

    assert "permissions:\n  contents: read" in workflow
    assert "fetch-depth: 0" in workflow
    assert (
        "gitleaks/gitleaks-action@"
        "e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e"
    ) in workflow
    assert 'condition = "AND"' in config
    assert "tests/jarvis_web_access/test_deployment" in config
    assert "tvly-synthetic-test" in config
    assert "paths = ['''.*'''" not in config


def test_constraints_are_path_free_and_cover_direct_dependencies() -> None:
    constraints = (ROOT / "constraints/python3.13.txt").read_text()

    for forbidden in ("file://", "-e ", "/home/", "/srv/"):
        assert forbidden not in constraints
    for package in (
        "alembic==",
        "mcp==",
        "psycopg==",
        "pytest==",
        "SQLAlchemy==",
        "setuptools==",
    ):
        assert package in constraints


def test_distribution_manifest_preserves_source_install_migrations() -> None:
    manifest = (ROOT / "MANIFEST.in").read_text()

    assert "include alembic.ini" in manifest
    assert "recursive-include migrations *.py" in manifest
    assert "include LICENSE" in manifest
