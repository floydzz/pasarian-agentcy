"""SQLAlchemy engine, session factory and declarative base."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


SCHEMA_REVISION = "20261015_workspaces"


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
    from .workspace import workspace_id, active_job, active_worker
    db = SessionLocal(info={"workspace_id": workspace_id(), "job_id": active_job.get(), "worker_id": active_worker.get()})
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    from . import models  # noqa: F401 — registers the mappers

    # The baseline bootstrap supports both fresh and existing installations.
    # Alembic reconciles additive columns/constraints and tracks applied versions.
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    with engine.connect() as connection:
        from sqlalchemy import text
        mysql = connection.dialect.name == "mysql"
        if mysql and connection.scalar(text("SELECT GET_LOCK('agentcy_schema_upgrade', 60)")) != 1:
            raise RuntimeError("Another schema upgrade is still running")
        try:
            Base.metadata.create_all(connection)
            connection.commit()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            connection.commit()
        finally:
            if connection.in_transaction():
                connection.rollback()
            if mysql:
                connection.execute(text("SELECT RELEASE_LOCK('agentcy_schema_upgrade')"))
                connection.commit()
