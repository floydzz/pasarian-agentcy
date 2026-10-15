"""Workspace scope is set by authentication and inherited by background work.

The session guard is a second boundary behind route authorization: it covers
relationship loads, aggregate queries, bulk updates and foreign-key writes.
Offline maintenance scripts deliberately use the legacy workspace (1).
"""
from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import ForeignKey, Integer, event, inspect, select
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria


@dataclass(frozen=True)
class Principal:
    user_id: int
    workspace_id: int
    role: str


principal: ContextVar[Principal | None] = ContextVar("principal", default=None)
worker_request: ContextVar[bool] = ContextVar("worker_request", default=False)
active_worker: ContextVar[str | None] = ContextVar("active_worker", default=None)
active_job: ContextVar[str | None] = ContextVar("active_job", default=None)


def workspace_id() -> int:
    actor = principal.get()
    return actor.workspace_id if actor else 1


class WorkspaceOwned:
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True, default=workspace_id)


@event.listens_for(Session, "do_orm_execute")
def scope_queries(execute_state):
    identity = execute_state.session.info.get("workspace_id")
    if identity is None:
        return  # Explicit administrative/test sessions, never a request session.
    if execute_state.is_select or execute_state.is_update or execute_state.is_delete:
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(WorkspaceOwned, lambda row: row.workspace_id == identity, include_aliases=True),
        )


@event.listens_for(Session, "before_flush")
def check_writes(db, flush_context, instances):
    identity = db.info.get("workspace_id")
    if identity is None:
        return
    if db.info.get("job_id"):
        from app.models import Job
        from app.clock import utcnow
        lease = db.connection().execute(select(Job.__table__.c.status, Job.__table__.c.worker_id, Job.__table__.c.lease_until).where(Job.__table__.c.id == db.info["job_id"]).with_for_update()).first()
        if not lease or lease.status != "running" or lease.worker_id != db.info.get("worker_id") or lease.lease_until < utcnow():
            raise HTTPException(409, "The job lease ended. Review its saved output before retrying.")
    for row in db.new.union(db.dirty).union(db.deleted):
        if not isinstance(row, WorkspaceOwned):
            continue
        state = inspect(row)
        if row in db.new and row.workspace_id is None:
            row.workspace_id = identity
        if row.workspace_id != identity or (state.attrs.workspace_id.history.deleted and state.attrs.workspace_id.history.deleted[0] != identity):
            raise HTTPException(404, "Record not found in this workspace")
        # A scoped row must never point at a foreign workspace's parent.
        for column in row.__table__.columns:
            if column.name == "workspace_id":
                continue
            value = getattr(row, column.name)
            for key in column.foreign_keys:
                target = key.column.table
                if value is not None and "workspace_id" in target.c:
                    found = db.connection().scalar(select(target.c.workspace_id).where(key.column == value))
                    if found != identity:
                        raise HTTPException(404, "Related record not found in this workspace")
        for column in row.__table__.columns:
            value = getattr(row, column.name)
            if column.name.endswith("url") and isinstance(value, str) and value.startswith("/media/"):
                require_media_scope(value, identity)


def require_media_scope(url: str, identity: int | None = None):
    identity = identity or workspace_id()
    if ".." in url.split("/") or "\\" in url:
        raise HTTPException(404, "Media not found")
    prefix = f"/media/w/{identity}/"
    if not url.startswith(prefix) and not (identity == 1 and not url.startswith("/media/w/")):
        raise HTTPException(404, "Media not found")
