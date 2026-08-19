import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from jarvis.state import Base, JarvisStateStore
from jarvis.state.database import create_session_factory


@pytest.fixture
def state_store() -> JarvisStateStore:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return JarvisStateStore(create_session_factory(engine))
