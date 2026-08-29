"""SQLAlchemy engine, session factory and declarative base."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    future=True,
    pool_pre_ping=True,  # long-running agent work can outlive a MySQL idle timeout
)

SessionLocal = sessionmaker(bind=engine, future=True, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency — one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    from . import models  # noqa: F401 — registers the mappers

    Base.metadata.create_all(engine)
    _add_missing_columns()


#: Columns added to tables that already exist in the wild. `create_all` only
#: creates whole tables, and the project has no migration tool, so a column
#: added to a shipped table has to be reconciled here or every existing
#: developer database silently keeps the old shape.
_LATE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("marketing_videos", "campaign_id", "INTEGER NULL"),
    ("marketing_videos", "use_broll", "BOOLEAN NOT NULL DEFAULT 0"),
    ("cinematic_trailer_shots", "product_surface", "VARCHAR(32) NOT NULL DEFAULT 'none'"),
    ("cinematic_trailers", "application_capture_url", "VARCHAR(1000) NULL"),
    ("cinematic_trailers", "soundtrack_url", "VARCHAR(1000) NULL"),
    ("cinematic_trailers", "product_reference_url", "VARCHAR(1000) NULL"),
    ("cinematic_trailers", "campaign_id", "INTEGER NULL"),
    ("marketing_videos", "product_reference_url", "VARCHAR(1000) NULL"),
    ("agent_settings", "context_turns", "INTEGER NULL"),
)


def _add_missing_columns() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, column, ddl in _LATE_COLUMNS:
            if table not in tables:
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            if column in existing:
                continue
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
