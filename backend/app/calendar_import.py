"""Validate the complete reviewed dataset before changing any calendar records."""
from __future__ import annotations
import hashlib
from datetime import date
import json
from pathlib import Path
from typing import Literal
from pydantic import Field, HttpUrl, field_validator
from sqlalchemy import select
from app.calendar_schemas import DateRange, STATES
from app.models import CalendarOccasion

DATA = Path(__file__).resolve().parents[1] / "data" / "calendar"

class OccasionRecord(DateRange):
    source_key: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=200)
    category: Literal["holiday", "school", "festival", "commercial"]
    states: list[str] = Field(min_length=1, max_length=16)
    source_url: HttpUrl
    source_revision: str = Field(min_length=1, max_length=80)
    verified_at: str
    publication_status: Literal["confirmed", "tentative", "withdrawn"]
    observed_for: str | None = None

    @field_validator("verified_at")
    @classmethod
    def verification_date(cls, value):
        date.fromisoformat(value)
        return value

    @field_validator("states")
    @classmethod
    def known_states(cls, values):
        if any(s not in STATES for s in values):
            raise ValueError("Unknown state in holiday dataset")
        return values


def import_calendar(db, directory: Path = DATA) -> int:
    records = [OccasionRecord.model_validate(row) for path in sorted(directory.glob("*.json")) for row in json.loads(path.read_text())]
    keys = [row.source_key for row in records]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate occasion source keys; calendar import cancelled")
    existing = {row.source_key: row for row in db.scalars(select(CalendarOccasion))}
    changed = 0
    for record in records:
        data = record.model_dump(mode="python")
        data["source_url"] = str(data["source_url"])
        # Content revisions catch date/applicability corrections even if a publisher reuses a URL.
        digest = hashlib.sha256(json.dumps(record.model_dump(mode="json", exclude={"verified_at", "source_revision"}), sort_keys=True).encode()).hexdigest()[:12]
        data["source_revision"] = f"{record.source_revision}:{digest}"
        row = existing.get(record.source_key)
        if row is None:
            db.add(CalendarOccasion(**data)); changed += 1
        elif any(getattr(row, key) != value for key, value in data.items()):
            for key, value in data.items():
                setattr(row, key, value)
            changed += 1
    db.commit()
    return changed
