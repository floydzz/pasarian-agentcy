from typing import Any
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, load_only
from app.clock import utcnow
from app.db import get_db
from app.jobs import job_read, submit
from app.models import Job, AICall

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobWrite(BaseModel):
    path: str = Field(max_length=255)
    payload: dict[str, Any] | None = None
    request_key: str = Field(min_length=8, max_length=80)


def find(db, identity, lock=False):
    query = select(Job).where(Job.id == identity)
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise HTTPException(404, "Job not found")
    return row


@router.post("", status_code=202)
def enqueue(payload: JobWrite, db: Session = Depends(get_db)):
    return job_read(submit(db, payload.path, payload.payload, payload.request_key))


@router.get("")
def listing(active: bool = False, limit: int = Query(default=30, ge=1, le=100), db: Session = Depends(get_db)):
    query = select(Job).options(load_only(Job.id, Job.path, Job.status, Job.error, Job.created_at, Job.updated_at)).order_by(Job.created_at.desc()).limit(limit)
    if active:
        query = query.where(Job.status.in_(["queued", "running", "interrupted"]))
    return [job_read(row, summary=True) for row in db.scalars(query)]


@router.get("/{job_id}")
def detail(job_id: str, after: int = Query(default=0, ge=0), include_usage: bool = False, db: Session = Depends(get_db)):
    row = find(db, job_id)
    result = job_read(row, after)
    result["calls"] = [{"id": c.id, "provider": c.provider, "model": c.model, "prompt_version": c.prompt_version,
                        "schema": c.schema_name, "request_id": c.request_id, "input_tokens": c.input_tokens,
                        "output_tokens": c.output_tokens, "duration_ms": c.duration_ms, "status": c.status,
                        "error_code": c.error_code, "evidence": c.evidence, "attempts": c.attempts, "estimated_cost_usd": c.estimated_cost_usd} for c in db.scalars(select(AICall).where(AICall.job_id == row.id).order_by(AICall.id))] if include_usage else []
    return result


@router.post("/{job_id}/cancel")
def cancel(job_id: str, db: Session = Depends(get_db)):
    row = find(db, job_id, True)
    if row.status != "queued":
        raise HTTPException(409, "Only queued work can be cancelled. Work already sent to a provider must finish so its output can be saved.")
    row.status, row.active_key, row.finished_at = "cancelled", None, utcnow()
    db.commit(); return job_read(row)


@router.post("/{job_id}/retry", status_code=202)
def retry(job_id: str, db: Session = Depends(get_db)):
    row = find(db, job_id, True)
    if row.status not in ("failed", "interrupted"):
        raise HTTPException(409, "Only failed or interrupted jobs can be retried")
    if row.path.startswith('/calendar/runs/'):
        from app.models import CalendarRun
        saved = db.get(CalendarRun, int(row.path.split('/')[3]))
        if saved and saved.status in ('failed', 'running'):
            saved.status = 'pending'
    # A retry is explicit: never automatically repeat an ambiguous paid call.
    return job_read(submit(db, row.path, row.payload, str(uuid4())))
