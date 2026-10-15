"""Import reviewed official occasions. Never scrapes or invents dates."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import SessionLocal
from app.calendar_import import import_calendar

if __name__ == "__main__":
    with SessionLocal() as db:
        print(f"Imported {import_calendar(db)} new or changed calendar records")
