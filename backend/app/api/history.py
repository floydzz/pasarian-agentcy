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
import threading

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.events import AgentEvent, EventSink
from app.clock import utcnow
from app.api.schemas import CreativeRead, RunDetail, RunRead
from app.config import get_settings
from app.db import get_db
from app.models import Asset, Campaign, Concept, Run, Variant

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

    Several agents now post here at once — concepts are generated in parallel
    and variants rendered in parallel — so the log is guarded. The lock is not
    about corrupting the list, which `append` would not do anyway; it is about
    keeping the recorded order and the streamed order the same. Without it a
    run could be replayed from history in an order nobody ever saw on screen.
    """

    def __init__(self, campaign: Campaign, kind: str) -> None:
        self.campaign_id = campaign.id
        self.campaign_name = campaign.name
        self.kind = kind
        self.started = utcnow()
        self.events: list[dict] = []
        self._guard = threading.Lock()

    def capture(self, event: AgentEvent) -> None:
        with self._guard:
            self.events.append(event.as_dict())

    def tee(self, sink: EventSink) -> EventSink:
        """Wrap a stream's sink so events are both sent and kept.

        Recorded and forwarded under one lock, so the two orderings agree.
        """

        def both(event: AgentEvent) -> None:
            with self._guard:
                self.events.append(event.as_dict())
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


@router.get("/creatives", response_model=list[CreativeRead])
def list_creatives(
    limit: int = 200,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[CreativeRead]:
    """Every creative made, newest first — the work rather than the log.

    `/runs` records what the machine did; this is what it produced. Joined all
    the way out to the campaign so the gallery can name each image without a
    request per row, which at a few hundred creatives is the difference
    between a page and a stampede.
    """
    rows = db.execute(
        select(Asset, Campaign.id, Campaign.name, Concept.theme, Variant.headline)
        .join(Variant, Asset.variant_id == Variant.id)
        .join(Concept, Variant.concept_id == Concept.id)
        .join(Campaign, Concept.campaign_id == Campaign.id)
        .where(Campaign.id == campaign_id if campaign_id is not None else True)
        .order_by(Asset.id.desc())
        .limit(max(1, min(limit, 500)))
    ).all()

    return [
        CreativeRead(
            id=asset.id,
            variant_id=asset.variant_id,
            media_url=asset.media_url,
            qa_status=asset.qa_status,
            qa_notes=asset.qa_notes,
            review_status=asset.review_status,
            created_at=asset.created_at,
            campaign_id=owner_id,
            campaign_name=owner_name,
            concept_theme=theme,
            headline=headline,
        )
        for asset, owner_id, owner_name, theme, headline in rows
    ]
