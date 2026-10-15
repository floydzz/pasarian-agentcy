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
os.environ["SERPAPI_KEY"] = ""
os.environ["SCRIPTED_DEMO"] = "false"
os.environ["CHROMA_HOST"] = ""

# And give the store somewhere of its own. Without this the suite embeds its
# fixtures straight into the developer's real `.chroma`, which pollutes that
# corpus and then fails outright once it holds vectors from a real provider:
# the demo embedder is 256-dimensional and nothing else is.
_CHROMA = tempfile.mkdtemp(prefix="agentcy-test-chroma-")
os.environ["CHROMA_PATH"] = _CHROMA
os.environ["BOOTSTRAP_TOKEN_PATH"] = os.path.join(_CHROMA, "setup-code")
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
    from sqlalchemy.engine import make_url
    test_url = make_url(TEST_DATABASE_URL)
    if test_url.get_backend_name() != "sqlite" and not (test_url.database or "").endswith("_test"):
        raise RuntimeError("Refusing to reset a database whose name does not end in _test")
    engine = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from app.models import Workspace
    with engine.begin() as connection:
        connection.execute(Workspace.__table__.insert().values(id=1, name="Test workspace", token_limit_per_job=250000, call_limit_per_job=100))
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    """A session rolled back after each test, so tests never see each other."""
    connection = engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(bind=connection, future=True)
    db = factory()
    from app.models import Workspace
    if db.get(Workspace, 1) is None:
        db.add(Workspace(id=1, name="Test workspace")); db.flush()
    try:
        yield db
    finally:
        db.close()
        # A failed flush (e.g. an IntegrityError test) already unwound the
        # transaction, so only roll back one that is still live.
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def legacy_api_actor(request):
    """Legacy tests exercise gates offline; security tests use real sessions."""
    from app.workspace import principal, worker_request, Principal
    if request.node.get_closest_marker("real_auth"):
        actor = principal.set(None)
        trusted = worker_request.set(False)
    else:
        actor = principal.set(Principal(1, 1, "owner"))
        trusted = worker_request.set(True)
    try:
        yield
    finally:
        worker_request.reset(trusted)
        principal.reset(actor)
