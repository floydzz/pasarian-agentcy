import atexit
import os
import shutil
import tempfile

# The suite exercises the complete API, including the dependency factories.
# Make those factories deterministic and offline even when a developer's .env
# points at a paid provider for a local run.
os.environ["LLM_PROVIDER"] = "demo"
os.environ["EMBEDDING_PROVIDER"] = "demo"
os.environ["MEDIA_PROVIDER"] = "demo"
os.environ["VIDEO_PROVIDER"] = "demo"

# And give the store somewhere of its own. Without this the suite embeds its
# fixtures straight into the developer's real `.chroma`, which pollutes that
# corpus and then fails outright once it holds vectors from a real provider:
# the demo embedder is 256-dimensional and nothing else is.
_CHROMA = tempfile.mkdtemp(prefix="agentcy-test-chroma-")
os.environ["CHROMA_PATH"] = _CHROMA
atexit.register(shutil.rmtree, _CHROMA, True)

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "mysql+pymysql://agentcy:agentcy_pw@127.0.0.1:3308/agentcy_test",
)


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    """A session rolled back after each test, so tests never see each other."""
    connection = engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(bind=connection, future=True)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        # A failed flush (e.g. an IntegrityError test) already unwound the
        # transaction, so only roll back one that is still live.
        if transaction.is_active:
            transaction.rollback()
        connection.close()
