import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "mysql+pymysql://agentcy:agentcy_pw@127.0.0.1:3307/agentcy_test",
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
