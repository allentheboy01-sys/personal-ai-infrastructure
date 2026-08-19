from email.message import EmailMessage
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from pdi.adapters.base import ProviderFact
from pdi.engine import SyncEngine
from pdi.identity import Matcher
from pdi.observation import (
    EnrichmentWorker,
    GmailMetadataExtractor,
    PostgreSQLObservationRepository,
)
from pdi.repository import PostgreSQLRepository
from tests.integration.database_guard import require_safe_test_database_url


ROOT = Path(__file__).resolve().parents[3]


class _SyncAdapter:
    provider_name = "gmail"

    def __init__(self, fact, raw):
        self.fact = fact
        self.raw = raw

    def connect(self):
        pass

    def scan(self):
        return (self.fact,)

    def open(self, fact):
        yield self.raw


class _Reader:
    def __init__(self, raw):
        self.raw = raw

    def open(self, source):
        yield self.raw


def test_gmail_sync_and_metadata_enrichment_persist_typed_resource_and_facts():
    engine = create_engine(require_safe_test_database_url())
    with engine.connect() as connection:
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    message = EmailMessage()
    message["Subject"] = "Synthetic integration subject"
    message["From"] = "from@example.invalid"
    message["To"] = "to@example.invalid"
    message.set_content("Synthetic integration body")
    raw = message.as_bytes()
    external_id = f"synthetic-gmail-{uuid4().hex}"
    fact = ProviderFact(
        "gmail", "message", external_id, "Synthetic integration subject",
        {"path": None, "size": None, "mime_type": "message/rfc822", "version_tag": None, "content_hash": None},
        {"internalDate": "1722470400000"},
    )
    core = PostgreSQLRepository(engine)
    SyncEngine(_SyncAdapter(fact, raw), Matcher(), core).sync_once()
    source = core.find_source("gmail", external_id)
    blob = core.get_blob(source.blob_id)
    asset = core.get_asset(blob.asset_id)
    assert asset.resource_type.value == "message"

    observations = PostgreSQLObservationRepository(engine)
    result = EnrichmentWorker(
        observations,
        GmailMetadataExtractor(_Reader(raw)),
        provider="gmail",
        resource_type="message",
    ).run_once(batch_size=10)
    assert result.processed == 1
    statements = observations.get_resource_statements(
        f"pdi:resource:{asset.id}",
        predicate=None,
        include_history=False,
        limit=10,
    )
    assert {statement.predicate for statement in statements} == {
        "gmail.subject", "gmail.from", "gmail.to", "gmail.internal_date"
    }

    asset_uuid = UUID(asset.id)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM resource_enrichments WHERE subject_asset_id=:id"), {"id": asset_uuid})
        connection.execute(text("DELETE FROM resource_statements WHERE subject_asset_id=:id"), {"id": asset_uuid})
        connection.execute(text("DELETE FROM asset_sources WHERE blob_id=:id"), {"id": UUID(blob.id)})
        connection.execute(text("DELETE FROM blobs WHERE id=:id"), {"id": UUID(blob.id)})
        connection.execute(text("DELETE FROM assets WHERE id=:id"), {"id": asset_uuid})
    engine.dispose()
