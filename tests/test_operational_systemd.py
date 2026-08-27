from pathlib import Path

from pdi.data_status import PIPELINE_REGISTRY
from pdi.operational import LOCK_PATH, PIPELINE_COMMANDS


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_UNITS = {
    "pdi-sync-nextcloud.service": ("provider.nextcloud.sync", "3600"),
    "pdi-sync-immich.service": ("provider.immich.sync", "3600"),
    "pdi-enrichment-nextcloud-text.service": (
        "enrichment.nextcloud_text", "3600"
    ),
    "pdi-enrichment-nextcloud-documents.service": (
        "enrichment.nextcloud_documents", "1800"
    ),
    "pdi-enrichment-file-metadata.service": (
        "enrichment.file_metadata", "3600"
    ),
    "pdi-enrichment-immich-geo.service": (
        "enrichment.immich_geo", "3600"
    ),
    "pdi-enrichment-immich.service": (
        "enrichment.immich_metadata", "3600"
    ),
    "pdi-enrichment-immich-ocr.service": (
        "enrichment.immich_ocr", "3600"
    ),
}


def test_formal_services_delegate_lock_to_operational_runner() -> None:
    for filename, (pipeline_key, timeout) in EXPECTED_UNITS.items():
        service = (ROOT / "deployment/systemd" / filename).read_text()
        assert service.count("ExecStart=") == 1
        assert "/usr/bin/flock" not in service
        assert str(LOCK_PATH) not in service
        assert (
            "ExecStart=/opt/pdi/.venv/bin/python "
            f"-m pdi.operational --pipeline-key {pipeline_key} "
            f"--lock-timeout {timeout}"
        ) in service


def test_formal_command_map_matches_registry_and_existing_cli_contracts() -> None:
    assert set(PIPELINE_COMMANDS) == set(PIPELINE_REGISTRY)
    assert PIPELINE_COMMANDS["provider.nextcloud.sync"] == (
        "-m", "pdi.main", "--provider", "nextcloud"
    )
    assert PIPELINE_COMMANDS["provider.immich.sync"] == (
        "-m", "pdi.main", "--provider", "immich"
    )
    assert PIPELINE_COMMANDS["provider.gmail.sync"] == (
        "-m", "pdi.main", "--provider", "gmail"
    )
    assert PIPELINE_COMMANDS["enrichment.gmail_metadata"] == (
        "-m", "pdi.enrichment", "--extractor", "gmail-metadata",
        "--batch-size", "500",
    )
    assert PIPELINE_COMMANDS["enrichment.nextcloud_documents"] == (
        "-m", "pdi.enrichment", "--extractor", "nextcloud-documents",
        "--batch-size", "100",
    )
    assert PIPELINE_COMMANDS["enrichment.immich_metadata"] == (
        "-m", "pdi.enrichment", "--batch-size", "20000"
    )
