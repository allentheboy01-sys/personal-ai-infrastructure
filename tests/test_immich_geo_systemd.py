from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_immich_geo_service_uses_frozen_runtime_contract() -> None:
    service = (
        ROOT
        / "deployment/systemd/pdi-enrichment-immich-geo.service"
    ).read_text()

    assert "Type=oneshot" in service
    assert "User=harry" in service
    assert "WorkingDirectory=/srv/projects/PDI" in service
    assert "EnvironmentFile=/etc/pdi/pdi.env" in service
    assert (
        "ExecStart=/usr/bin/flock --exclusive --wait 3600 "
        "/run/lock/pdi-sync.lock "
        "/srv/projects/PDI/.venv/bin/python -m pdi.enrichment "
        "--extractor immich-geo --batch-size 20000"
    ) in service
    assert "TimeoutStartSec=90m" in service
    assert "UMask=0077" in service
    assert "StandardOutput=journal" in service
    assert "StandardError=journal" in service


def test_immich_geo_timer_uses_frozen_schedule() -> None:
    timer = (
        ROOT
        / "deployment/systemd/pdi-enrichment-immich-geo.timer"
    ).read_text()

    assert "OnCalendar=*-*-* 05:30:00" in timer
    assert "Persistent=true" in timer
    assert "Unit=pdi-enrichment-immich-geo.service" in timer
    assert "WantedBy=timers.target" in timer
