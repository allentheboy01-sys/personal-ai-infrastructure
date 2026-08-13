from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_formal_jarvis_whitelist_has_exactly_five_read_only_pdi_tools() -> None:
    text = (ROOT / "deployment/jarvis/config.yaml").read_text()
    expected = {
        "pdi_list_recent_resources",
        "pdi_search_resources",
        "pdi_get_resource",
        "pdi_aggregate_resources",
        "pdi_get_resource_observations",
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
