from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_formal_jarvis_whitelist_has_exactly_six_read_only_pdi_tools() -> None:
    text = (ROOT / "deployment/jarvis/config.yaml").read_text()
    expected = {
        "pdi_list_recent_resources",
        "pdi_search_resources",
        "pdi_get_resource",
        "pdi_aggregate_resources",
        "pdi_get_resource_observations",
        "pdi_retrieve_resources",
    }
    configured = {
        line.strip()[2:]
        for line in text.splitlines()
        if line.strip().startswith("- pdi_")
    }
    assert configured == expected
    assert "resources: false" in text
    assert "prompts: false" in text
    for forbidden in ("filesystem", "browser", "memory", "scheduler"):
        assert f"- {forbidden}" not in text


def test_formal_pdi_child_receives_only_required_pdi_configuration() -> None:
    text = (ROOT / "deployment/jarvis/pdi-mcp").read_text()

    for required in (
        "DATABASE__URL",
        "IMMICH__URL",
        "IMMICH__API_KEY",
    ):
        assert f'{required}="${required}"' in text

    assert "DEEPSEEK_API_KEY" not in text
