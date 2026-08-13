from types import SimpleNamespace

import pytest

import pdi.enrichment as enrichment


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class FakeWorker:
    calls: list[tuple[object, object, int]] = []

    def __init__(self, repository, extractor) -> None:
        self.repository = repository
        self.extractor = extractor

    def run_once(self, *, batch_size: int):
        self.calls.append((self.repository, self.extractor, batch_size))
        return SimpleNamespace(
            discovered=1,
            processed=1,
            skipped=0,
            failed=0,
            statement_writes=1,
            deactivated_statements=0,
        )


@pytest.fixture
def composition(monkeypatch):
    FakeWorker.calls.clear()
    engine = FakeEngine()
    repository = object()
    monkeypatch.setattr(enrichment, "load_database_url", lambda: "db-url")
    monkeypatch.setattr(
        enrichment,
        "create_postgres_engine",
        lambda url: engine,
    )
    monkeypatch.setattr(
        enrichment,
        "PostgreSQLObservationRepository",
        lambda configured_engine: repository,
    )
    monkeypatch.setattr(enrichment, "EnrichmentWorker", FakeWorker)
    return engine, repository


def test_default_composition_remains_metadata_only(
    monkeypatch,
    composition,
) -> None:
    engine, repository = composition
    metadata_extractor = object()
    monkeypatch.setattr(
        enrichment,
        "ImmichMetadataExtractor",
        lambda: metadata_extractor,
    )
    monkeypatch.setattr(
        enrichment,
        "load_immich_settings",
        lambda: pytest.fail("default must not load Immich OCR settings"),
    )
    monkeypatch.setattr(
        enrichment,
        "ImmichOCRReader",
        lambda settings: pytest.fail("default must not construct OCR reader"),
    )

    assert enrichment.main(["--batch-size", "7"]) == 0
    assert FakeWorker.calls == [(repository, metadata_extractor, 7)]
    assert engine.disposed is True


def test_explicit_ocr_selector_builds_reader_and_extractor(
    monkeypatch,
    composition,
) -> None:
    engine, repository = composition
    settings = object()
    reader = object()
    extractor = object()
    monkeypatch.setattr(
        enrichment,
        "load_immich_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        enrichment,
        "ImmichOCRReader",
        lambda configured_settings: (
            reader
            if configured_settings is settings
            else pytest.fail("wrong settings")
        ),
    )
    monkeypatch.setattr(
        enrichment,
        "ImmichOCRExtractor",
        lambda configured_reader: (
            extractor
            if configured_reader is reader
            else pytest.fail("wrong reader")
        ),
    )

    assert enrichment.main(
        ["--extractor", "immich-ocr", "--batch-size", "11"]
    ) == 0
    assert FakeWorker.calls == [(repository, extractor, 11)]
    assert engine.disposed is True


def test_ocr_configuration_failure_still_disposes_engine(
    monkeypatch,
    composition,
) -> None:
    engine, _ = composition

    def fail():
        raise RuntimeError("Immich OCR settings missing")

    monkeypatch.setattr(enrichment, "load_immich_settings", fail)
    with pytest.raises(RuntimeError, match="settings missing"):
        enrichment.main(["--extractor", "immich-ocr"])
    assert FakeWorker.calls == []
    assert engine.disposed is True


@pytest.mark.parametrize("batch_size", [0, -1])
def test_rejects_invalid_batch_before_creating_engine(
    monkeypatch,
    batch_size,
) -> None:
    monkeypatch.setattr(
        enrichment,
        "create_postgres_engine",
        lambda url: pytest.fail("engine must not be created"),
    )
    with pytest.raises(SystemExit, match="--batch-size must be positive"):
        enrichment.main(["--batch-size", str(batch_size)])
