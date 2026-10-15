"""Durable job submission and the adapter to existing, gated application routes.

Only catalogued operations may run. The worker uses the same FastAPI dependency
and validation path as an HTTP request, with an explicit trusted actor context.
No request cookies, API keys, arbitrary URLs or executable closures are stored.
"""
from __future__ import annotations
import hashlib
import re
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.clock import utcnow
from app.models import Campaign, CalendarRun, CinematicTrailer, Concept, Conversation, DemoVideo, Job, MarketingVideo, Asset, Variant, Workspace
from app.workspace import principal

CATALOG = (
    r"/campaigns/\d+/(?:plan|generate|render)(?:/stream)?",
    r"/campaigns/\d+/videos/render(?:/stream)?",
    r"/videos/render(?:/stream)?", r"/videos/\d+/redo",
    r"/demo-videos/render", r"/demo-videos/\d+/redo",
    r"/assets/\d+/redo", r"/concepts/\d+/revise",
    r"/calendar/runs/\d+/stream", r"/conversations/\d+/messages",
    r"/cinematic-trailers/\d+/(?:submit|refresh|compose|shots/regenerate|shots/\d+/regenerate)",
    r"/trends/scrape(?:\?source_id=\d+)?",
)


def is_operation(path):
    operation = path.partition("?")[0]
    return any(re.fullmatch(pattern, operation) for pattern in CATALOG)


def resource(db, path):
    parts = path.split("/")
    model = {"campaigns": Campaign, "videos": MarketingVideo, "demo-videos": DemoVideo, "assets": Asset,
             "concepts": Concept, "conversations": Conversation, "cinematic-trailers": CinematicTrailer}.get(parts[1])
    if parts[1:3] == ["calendar", "runs"]:
        model, identity = CalendarRun, int(parts[3])
    else:
        identity = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
    if identity and model:
        row = db.get(model, identity)
        if row is None:
            raise HTTPException(404, "Record not found")
        campaign_id = getattr(row, "campaign_id", None)
        if isinstance(row, Campaign):
            campaign_id = row.id
        if isinstance(row, Concept):
            campaign_id = row.campaign_id
        if isinstance(row, Asset):
            variant = db.get(Variant, row.variant_id)
            campaign_id = db.get(Concept, variant.concept_id).campaign_id
        if campaign_id:
            return f"campaign:{campaign_id}"
        return f"{model.__tablename__}:{identity}"
    return f"operation:{parts[1]}"


def submit(db, path, payload, request_key):
    if len(path) > 255 or payload is not None and not isinstance(payload, dict):
        raise HTTPException(422, "Use a supported path and a JSON object payload")
    if not is_operation(path):
        raise HTTPException(422, "This operation cannot run as a background job")
    if not isinstance(request_key, str) or not 8 <= len(request_key) <= 80:
        raise HTTPException(422, "Use a request key between 8 and 80 characters")
    actor = principal.get()
    # Serialize tiny enqueue transactions so the workspace queue cap is exact.
    db.scalar(select(Workspace.id).where(Workspace.id == actor.workspace_id).with_for_update())
    key = resource(db, path)
    previous = db.scalar(select(Job).where(Job.request_key == request_key))
    if previous:
        if previous.path != path or previous.payload != payload:
            raise HTTPException(409, "This request key belongs to a different operation")
        return previous
    running = db.scalar(select(Job).where(Job.active_key == key))
    if running:
        if running.path == path and running.payload == payload:
            return running
        raise HTTPException(409, "Another operation is already running for this campaign or resource")
    if db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(["queued", "running"]))) >= 10:
        raise HTTPException(429, "Your workspace already has ten jobs waiting or running")
    row = Job(id=str(uuid4()), user_id=actor.user_id, path=path, payload=payload, request_key=request_key, active_key=key)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.scalar(select(Job).where(Job.request_key == request_key))
        if previous and previous.path == path and previous.payload == payload:
            return previous
        running = db.scalar(select(Job).where(Job.active_key == key))
        if running and running.path == path and running.payload == payload:
            return running
        raise HTTPException(409, "Another request has already started this operation")
    return row


def job_read(row, after=0, *, summary=False):
    return {"id": row.id, "path": row.path, "status": row.status,
            "created_at": row.created_at.isoformat() + "Z", "updated_at": row.updated_at.isoformat() + "Z",
            "events": [] if summary else row.events[after:], "cursor": 0 if summary else len(row.events), "result": None if summary else row.result, "error": row.error}
