"""Test-only ASGI host for the actual production Vite artifact."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from jarvis.runtime import MockRuntimeAdapter
from jarvis.state import Base
from jarvis.web import JarvisWebSettings, TestAuthAdapter, create_app


ROOT = Path(__file__).resolve().parents[2]
engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(engine)
app = create_app(
    engine=engine,
    settings=JarvisWebSettings("http://127.0.0.1:4174", ROOT / "apps/jarvis-web/dist"),
    auth_adapter=TestAuthAdapter(),
    runtime=MockRuntimeAdapter(),
)
