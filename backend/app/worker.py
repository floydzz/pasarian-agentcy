"""Run with `python -m app.worker`; independent of browser and web lifetime."""
from __future__ import annotations
import asyncio
from contextvars import copy_context
from datetime import timedelta
import json
import logging
import signal
import threading
import time
from uuid import uuid4

from sqlalchemy import select, update, delete, or_, text
from sqlalchemy.exc import SQLAlchemyError
from app.clock import utcnow
from app.config import get_settings
from app.db import SessionLocal, SCHEMA_REVISION
from app.jobs import is_operation
from app.models import Job, Membership, User, Campaign, CalendarRun, WorkerHeartbeat, LoginAttempt, LoginSession
from app.workspace import Principal, active_job, active_worker, principal, worker_request
from app.telemetry import meter, make_meter

log = logging.getLogger(__name__)
STOP = threading.Event()
WORKER_ID = str(uuid4())
LAST_CLEANUP = 0.0


def touch_worker(db):
    global LAST_CLEANUP
    if time.monotonic() - LAST_CLEANUP > 60:
        now = utcnow()
        db.execute(delete(LoginSession).where(or_(LoginSession.expires_at < now, LoginSession.last_seen < now - timedelta(hours=get_settings().session_idle_hours))))
        db.execute(delete(LoginAttempt).where(LoginAttempt.reset_at < now))
        db.execute(delete(WorkerHeartbeat).where(WorkerHeartbeat.last_seen < now - timedelta(days=1)))
        LAST_CLEANUP = time.monotonic()
    row = db.get(WorkerHeartbeat, WORKER_ID)
    if row is None:
        db.add(WorkerHeartbeat(id=WORKER_ID, last_seen=utcnow()))
    else:
        row.last_seen = utcnow()
    db.commit()


def reset_transients(db, job, calendar_status="failed"):
    if job.path.startswith("/campaigns/") and "/plan" in job.path:
        db.execute(update(Campaign).where(Campaign.id == int(job.path.split('/')[2]), Campaign.workspace_id == job.workspace_id, Campaign.status == "planning").values(status="draft"))
    if job.path.startswith("/calendar/runs/"):
        db.execute(update(CalendarRun).where(CalendarRun.id == int(job.path.split('/')[3]), CalendarRun.workspace_id == job.workspace_id, CalendarRun.status == "running").values(status=calendar_status))


def recover_stale(db):
    rows = list(db.scalars(select(Job).where(Job.status == "running", Job.lease_until < utcnow()).with_for_update(skip_locked=True)))
    for row in rows:
        row.status, row.active_key, row.finished_at = "interrupted", None, utcnow()
        row.error = "The worker stopped before confirming completion. Saved output is retained. Review it before retrying; an unfinished provider call may already have been charged."
        reset_transients(db, row, "pending")
    db.commit()


def claim():
    with SessionLocal() as db:
        touch_worker(db)
        recover_stale(db)
        row = db.scalar(select(Job).where(Job.status == "queued").order_by(Job.created_at, Job.id).with_for_update(skip_locked=True).limit(1))
        if row is None:
            return None
        row.status, row.worker_id, row.started_at = "running", str(uuid4()), utcnow()
        row.lease_until = utcnow() + timedelta(seconds=get_settings().job_lease_seconds)
        db.commit()
        return row


def heartbeat(job, stopped):
    while not stopped.wait(max(1, get_settings().job_lease_seconds // 3)):
        try:
            with SessionLocal() as db:
                touch_worker(db)
                db.execute(update(Job).where(Job.id == job.id, Job.worker_id == job.worker_id, Job.status == "running").values(lease_until=utcnow() + timedelta(seconds=get_settings().job_lease_seconds)))
                db.commit()
        except Exception:
            log.exception("job heartbeat failed job_id=%s", job.id)


def persist_line(job, line):
    with SessionLocal(info={"workspace_id": job.workspace_id}) as db:
        row = db.scalar(select(Job).where(Job.id == job.id, Job.worker_id == job.worker_id, Job.status == "running").with_for_update())
        if row is None:
            raise RuntimeError("Job lease was lost")
        if line.get("kind") == "event":
            from app.agents.events import public_event
            if line.get("data", {}).get("terminal_failure"):
                log.error("agent operation failed job_id=%s", row.id)
                row.error = "The operation only completed part of its work. Review saved output and retry the unfinished work."
            line = public_event(line)
            row.events = [*row.events, line]
        elif line.get("kind") == "result":
            row.result = line["__response__"] if "__response__" in line else {key: value for key, value in line.items() if key != "kind"}
        elif line.get("kind") == "error":
            log.error("job reported failure job_id=%s detail=%s", row.id, line.get("detail"))
            row.error = "The operation failed. Review saved output and retry the unfinished work."
        db.commit()


async def invoke(job):
    from app.main import app
    done = asyncio.Event()
    sent = False
    response_status, stream = 500, False
    buffer = b""
    body = json.dumps(job.payload).encode() if job.payload is not None else b""

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await done.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal buffer, response_status, stream
        if message["type"] == "http.response.start":
            response_status = message["status"]
            stream = any(name == b"content-type" and b"ndjson" in value for name, value in message["headers"])
        if message["type"] != "http.response.body":
            return
        buffer += message.get("body", b"")
        if stream:
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                if raw.strip():
                    await asyncio.to_thread(persist_line, job, json.loads(raw))
        if not message.get("more_body", False):
            if buffer.strip():
                payload = json.loads(buffer)
                if response_status >= 400:
                    raise RuntimeError(f"Operation refused ({response_status}): {payload.get('detail', '')}")
                await asyncio.to_thread(persist_line, job, payload if stream else {"kind": "result", "__response__": payload})
            done.set()

    path, _, query = job.path.partition("?")
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": "/api" + path, "raw_path": ("/api" + path).encode(), "query_string": query.encode(), "root_path": "",
             "headers": [(b"host", b"worker"), (b"content-type", b"application/json")], "client": ("worker", 0), "server": ("worker", 80)}
    await app(scope, receive, send)


def execute(job):
    with SessionLocal() as db:
        user = db.get(User, job.user_id)
        membership = db.scalar(select(Membership).where(Membership.user_id == job.user_id, Membership.workspace_id == job.workspace_id))
    stopped = threading.Event()
    beat = threading.Thread(target=heartbeat, args=(job, stopped), daemon=True); beat.start()
    tokens = []
    try:
        if not membership or not user or user.disabled or not is_operation(job.path):
            raise RuntimeError("Job actor no longer has access")
        run_meter = make_meter(job.workspace_id)
        tokens = [(principal, principal.set(Principal(user.id, job.workspace_id, membership.role))),
                  (worker_request, worker_request.set(True)), (active_job, active_job.set(job.id)), (active_worker, active_worker.set(job.worker_id)), (meter, meter.set(run_meter))]
        asyncio.run(invoke(job))
        with SessionLocal() as db:
            row = db.get(Job, job.id)
            if row.worker_id != job.worker_id or row.status != "running":
                return
            row.status = "failed" if row.error or row.result is None else "succeeded"
            if row.result is None and not row.error:
                row.error = "The operation ended without a confirmed result. Review its saved output before retrying."
            if row.status == "failed":
                reset_transients(db, row)
            row.finished_at, row.active_key = utcnow(), None
            db.commit()
    except Exception:
        log.exception("job failed job_id=%s", job.id)
        with SessionLocal() as db:
            row = db.get(Job, job.id)
            if row.worker_id == job.worker_id and row.status == "running":
                row.status, row.active_key, row.finished_at = "failed", None, utcnow()
                row.error = "The operation could not complete. Review its saved output before retrying."
                reset_transients(db, row)
                db.commit()
    finally:
        stopped.set(); beat.join(timeout=5)
        for variable, token in reversed(tokens):
            variable.reset(token)


def main():
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    waiting = False
    while not STOP.is_set():
        try:
            with SessionLocal() as db:
                if db.scalar(text("SELECT version_num FROM alembic_version")) == SCHEMA_REVISION:
                    break
        except SQLAlchemyError:
            pass  # The API initializer owns migrations; this is expected at first boot.
        if not waiting:
            log.info("Waiting for the application schema before accepting jobs")
            waiting = True
        STOP.wait(1)
    while not STOP.is_set():
        try:
            job = claim()
            if job:
                execute(job)
            else:
                STOP.wait(get_settings().job_poll_seconds)
        except Exception:
            log.exception("worker polling failed")
            STOP.wait(5)


if __name__ == "__main__":
    import sys
    if "--health" in sys.argv:
        from sqlalchemy import func
        with SessionLocal() as db:
            available = db.scalar(select(func.count()).select_from(WorkerHeartbeat).where(WorkerHeartbeat.last_seen >= utcnow() - timedelta(seconds=120)))
        raise SystemExit(0 if available else 1)
    main()
