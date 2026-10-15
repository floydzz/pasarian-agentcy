"""Disposable offline browser-test installation. Never opens an existing DB."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
temporary = tempfile.TemporaryDirectory(prefix="agentcy-browser-")
directory = Path(temporary.name)
os.environ.update({"DATABASE_URL": f"sqlite:///{directory / 'browser.db'}", "CHROMA_PATH": str(directory / "chroma"),
                   "CHROMA_HOST": "", "ASSETS_PATH": str(directory / "assets"), "LLM_PROVIDER": "demo", "EMBEDDING_PROVIDER": "demo",
                   "MEDIA_PROVIDER": "demo", "VIDEO_PROVIDER": "demo", "SCRIPTED_DEMO": "false", "SERPAPI_KEY": "",
                   "SESSION_SECURE": "false", "PUBLIC_ORIGIN": "", "BOOTSTRAP_TOKEN_PATH": str(directory / "setup-code")})

from app.db import create_all, engine, SessionLocal
from app.models import Campaign, User, Workspace, Membership, BrandProfile
from app.security import hash_password
from app.calendar_import import import_calendar
from app.api.deps import get_store
from app.brand_profile import as_markdown, PROFILE_SOURCE

create_all()  # The real worker waits for the fully tracked schema revision.
with SessionLocal() as db:
    db.get(Workspace, 1).name = "Browser test workspace"
    db.flush()
    user = User(email="browser@example.test", name="Browser Tester", password_hash=hash_password("browser-test-password"))
    db.add(user); db.flush(); db.add(Membership(user_id=user.id, workspace_id=1, role="owner"))
    profile = BrandProfile(company_name="Browser Brand", industry="Retail", description="Malaysian retail brand", brand_voice="Clear, friendly and factual",
        target_audience="Malaysian adults", products=[{"name": "Starter bundle", "description": "Our approved starter bundle", "price": "RM 50"}],
        approved_claims="Use only supplied product facts", restrictions="No medical or performance claims")
    db.add(profile); db.add(Campaign(name="Browser campaign", brief="Promote the Starter bundle for Malaysian shoppers.")); db.commit()
    get_store().replace_company_kb(as_markdown(profile), source=PROFILE_SOURCE)
    import_calendar(db)

worker = subprocess.Popen([sys.executable, "-m", "app.worker"], cwd=root, env={**os.environ, "PYTHONPATH": str(root)})
try:
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8123, log_level="warning")
finally:
    worker.terminate()
    try:
        worker.wait(timeout=10)
    except subprocess.TimeoutExpired:
        worker.kill(); worker.wait()
    engine.dispose()
    temporary.cleanup()
