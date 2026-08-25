"""The record of what the machine has done, and the routes that read it back.

A console you have to be watching is a console that forgets. Every planning
pass and every crew run writes a row here with the agent events exactly as the
console received them, so a run can be reopened later and replayed rather than
summarised — which is the difference between an audit trail and a status line.

Recording is deliberately best-effort: a run that produced real work must never
be lost because the bookkeeping for it failed.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.events import AgentEvent, EventSink
from app.clock import utcnow
from app.api.schemas import RunDetail, RunRead
from app.config import get_settings
from app.db import get_db
from app.models import Campaign, Run

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["history"])

PLAN = "plan"
GENERATE = "generate"
RENDER = "render"


class RunLog:
    """Collects a run's events as they happen, then writes the row.

    The campaign's name and id are copied at construction because the worker
    thread must not touch the session, and the row has to survive the campaign
    being deleted anyway.
    """

    def __init__(self, campaign: Campaign, kind: str) -> None:
        self.campaign_id = campaign.id
        self.campaign_name = campaign.name
        self.kind = kind
        self.started = utcnow()
        self.events: list[dict] = []

    def capture(self, event: AgentEvent) -> None:
        self.events.append(event.as_dict())

    def tee(self, sink: EventSink) -> EventSink:
        """Wrap a stream's sink so events are both sent and kept."""

        def both(event: AgentEvent) -> None:
            self.capture(event)
            sink(event)

        return both

    # -- writing -----------------------------------------------------------

    def succeeded(self, db: Session, summary: str, **counts: int) -> None:
        self._write(db, status="succeeded", summary=summary, **counts)

    def failed(self, db: Session, error: str, **counts: int) -> None:
        self._write(
            db,
            status="failed",
            summary=error.strip() or "The run failed without saying why.",
            error=error,
            **counts,
        )

    def _write(
        self,
        db: Session,
        *,
        status: str,
        summary: str,
        error: str | None = None,
        **counts: int,
    ) -> None:
        elapsed = (utcnow() - self.started).total_seconds()
        row = Run(
            campaign_id=self.campaign_id,
            campaign_name=self.campaign_name,
            kind=self.kind,
            status=status,
            started_at=self.started,
            duration_ms=int(elapsed * 1000),
            summary=summary,
            events=self.events,
            error=error,
            provider=get_settings().llm_provider,
            **counts,
        )
        try:
            db.add(row)
            db.commit()
        except Exception:
            # The work itself is already committed. Losing the history entry is
            # a bad day; losing the campaign's variants because history failed
            # would be a much worse one.
            log.exception("could not record the %s run for %s", self.kind, self.campaign_name)
            db.rollback()


# -- routes ----------------------------------------------------------------


@router.get("/runs", response_model=list[RunRead])
def list_runs(
    limit: int = 60,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[Run]:
    """Newest first. Events are omitted here — see `/runs/{id}` for those."""
    query = select(Run).order_by(Run.id.desc()).limit(max(1, min(limit, 200)))
    if campaign_id is not None:
        query = query.where(Run.campaign_id == campaign_id)
    return list(db.scalars(query))


@router.get("/runs/{run_id}", response_model=RunDetail)
def read_run(run_id: int, db: Session = Depends(get_db)) -> Run:
    row = db.get(Run, run_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no run {run_id}")
    return row
