from pathlib import Path

from pdi.data_status import FORMAL_PIPELINE_REGISTRY, PIPELINE_REGISTRY
from pdi.operational import LOCK_PATH, PIPELINE_COMMANDS


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_UNITS = {
    "pdi-sync-nextcloud.service": ("provider.nextcloud.sync", "3600"),
    "pdi-sync-immich.service": ("provider.immich.sync", "3600"),
    "pdi-sync-nextcloud-incremental.service": (
        "provider.nextcloud.incremental", "300"
    ),
    "pdi-sync-immich-incremental.service": (
        "provider.immich.incremental", "300"
    ),
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
    assert set(PIPELINE_COMMANDS) == set(FORMAL_PIPELINE_REGISTRY)
    assert PIPELINE_COMMANDS["provider.nextcloud.sync"] == (
        "-m", "pdi.main", "--provider", "nextcloud", "--operation", "full"
    )
    assert PIPELINE_COMMANDS["provider.immich.sync"] == (
        "-m", "pdi.main", "--provider", "immich", "--operation", "full"
    )
    assert PIPELINE_COMMANDS["provider.gmail.sync"] == (
        "-m", "pdi.main", "--provider", "gmail", "--operation", "full"
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
    for provider in ("nextcloud", "immich"):
        for key_suffix, operation in (
            ("incremental", "incremental"),
            ("bootstrap", "bootstrap"),
            ("recovery", "recover"),
        ):
            assert PIPELINE_COMMANDS[f"provider.{provider}.{key_suffix}"] == (
                "-m", "pdi.main", "--provider", provider,
                "--operation", operation,
            )
    assert "provider.nextcloud.bootstrap" not in PIPELINE_REGISTRY


def test_incremental_timers_are_staggered_persistent_and_never_repair() -> None:
    expected = {
        "pdi-sync-nextcloud-incremental.timer": "OnCalendar=*:0/5",
        "pdi-sync-immich-incremental.timer": "OnCalendar=*:2/5",
    }
    for filename, cadence in expected.items():
        timer = (ROOT / "deployment/systemd" / filename).read_text()
        assert cadence in timer
        assert "Persistent=true" in timer
        assert "bootstrap" not in timer
        assert "recovery" not in timer


def test_existing_full_timer_cadences_are_unchanged() -> None:
    nextcloud = (ROOT / "deployment/systemd/pdi-sync-nextcloud.timer").read_text()
    immich = (ROOT / "deployment/systemd/pdi-sync-immich.timer").read_text()
    assert "OnCalendar=*-*-* 02:15:00" in nextcloud
    assert "OnCalendar=*-*-* 05:15:00" in immich
