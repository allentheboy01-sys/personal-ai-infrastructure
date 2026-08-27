from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_nextcloud_documents_service_uses_frozen_runtime_contract() -> None:
    service = (
        ROOT
        / "deployment/systemd/pdi-enrichment-nextcloud-documents.service"
    ).read_text()

    assert "Type=oneshot" in service
    assert "User=pdi" in service
    assert "Group=pdi" in service
    assert "WorkingDirectory=/opt/pdi" in service
    assert "EnvironmentFile=/etc/pdi/pdi.env" in service
    assert (
        "ExecStart=/opt/pdi/.venv/bin/python -m pdi.operational "
        "--pipeline-key enrichment.nextcloud_documents --lock-timeout 1800"
    ) in service
    assert "TimeoutStartSec=30m" in service
    assert "UMask=0077" in service
    assert "StandardOutput=journal" in service
    assert "StandardError=journal" in service


def test_nextcloud_documents_timer_uses_frozen_schedule() -> None:
    timer = (
        ROOT
        / "deployment/systemd/pdi-enrichment-nextcloud-documents.timer"
    ).read_text()

    assert "OnCalendar=*-*-* 03:15:00" in timer
    assert "Persistent=true" in timer
    assert "Unit=pdi-enrichment-nextcloud-documents.service" in timer
    assert "WantedBy=timers.target" in timer
