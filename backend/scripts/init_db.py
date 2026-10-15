"""Create the MySQL schema.

    python scripts/init_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import create_all, engine, SessionLocal  # noqa: E402

if __name__ == "__main__":
    create_all()
    from app.security import ensure_bootstrap_token
    ensure_bootstrap_token()
    from app.calendar_import import import_calendar
    with SessionLocal() as db:
        import_calendar(db)
    print(f"schema created on {engine.url.render_as_string(hide_password=True)}")
