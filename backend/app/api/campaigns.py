"""Campaign routes, including the plan approval gate.

The gate is the point of the whole design: the planner may propose, but nothing
moves to generation until a human has approved at least one concept. Status
changes happen here and only here, one step at a time.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.planner import PlanningAgent, PlanningError, PlanResult
from app.api.deps import get_campaign_or_404, get_planner
from app.api.conversions import to_domain_concept
from app.api.history import PLAN, RunLog
from app.api.streaming import event_stream
from app.api.schemas import (
    CampaignCreate,
    CampaignRead,
    ConceptDecision,
    ConceptRead,
    ConceptRevision,
    PlanRead,
)
from app.db import get_db
from app.domain import CampaignStatus, ConceptStatus
from app.models import Campaign, Concept

router = APIRouter(prefix="/api", tags=["campaigns"])


@router.post("/campaigns", response_model=CampaignRead, status_code=201)
def create_campaign(payload: CampaignCreate, db: Session = Depends(get_db)) -> Campaign:
    campaign = Campaign(
        name=payload.name, brief=payload.brief, source_event=payload.source_event
    )
    db.add(campaign)
    db.commit()
    return campaign


@router.get("/campaigns", response_model=list[CampaignRead])
def list_campaigns(db: Session = Depends(get_db)) -> list[Campaign]:
    return list(db.scalars(select(Campaign).order_by(Campaign.id.desc())))


@router.get("/campaigns/{campaign_id}", response_model=CampaignRead)
def read_campaign(campaign_id: int, db: Session = Depends(get_db)) -> Campaign:
    return get_campaign_or_404(db, campaign_id)


@router.get("/campaigns/{campaign_id}/concepts", response_model=list[ConceptRead])
def list_concepts(campaign_id: int, db: Session = Depends(get_db)) -> list[Concept]:
    get_campaign_or_404(db, campaign_id)
    return list(
        db.scalars(
            select(Concept).where(Concept.campaign_id == campaign_id).order_by(Concept.id)
        )
    )


@router.post("/campaigns/{campaign_id}/plan", response_model=PlanRead)
def plan_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    planner: PlanningAgent = Depends(get_planner),
) -> PlanRead:
    campaign = get_campaign_or_404(db, campaign_id)
    _require_status(campaign, CampaignStatus.DRAFT, action="planning")

    campaign.status = CampaignStatus.PLANNING
    db.flush()

    record = RunLog(campaign, PLAN)
    try:
        result = planner.plan(
            campaign.brief, source_event=campaign.source_event, sink=record.capture
        )
    except PlanningError as error:
        # Planning failed, so the brief is still the thing to fix — hand the
        # campaign back to the human as a draft rather than stranding it.
        campaign.status = CampaignStatus.DRAFT
        db.commit()
        record.failed(db, str(error))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error

    stored = _store_plan(db, campaign, result)
    _record_plan(db, record, stored)
    return stored


def _store_plan(db: Session, campaign: Campaign, result: PlanResult) -> PlanRead:
    concepts = [
        Concept(
            campaign_id=campaign.id,
            theme=drafted.theme,
            format=drafted.format,
            trend_rationale=drafted.trend_rationale,
            brand_rationale=drafted.brand_rationale,
            variant_count=drafted.variant_count,
            variation_axes=drafted.variation_axes,
        )
        for drafted in result.concepts
    ]
    db.add_all(concepts)

    if campaign.auto_approve_plan:
        # Auto-mode bypasses the screen, not the state machine: the concepts
        # still carry an explicit approved status, so downstream code and the
        # audit trail cannot tell the difference between this and a human who
        # approved everything.
        for concept in concepts:
            concept.status = ConceptStatus.APPROVED
        campaign.status = CampaignStatus.GENERATING
    else:
        campaign.status = CampaignStatus.PENDING_PLAN_APPROVAL

    db.commit()

    return PlanRead(
        strategy_summary=result.strategy_summary,
        concepts=[ConceptRead.model_validate(concept) for concept in concepts],
    )


@router.post("/campaigns/{campaign_id}/plan/stream")
def plan_campaign_streaming(
    campaign_id: int,
    db: Session = Depends(get_db),
    planner: PlanningAgent = Depends(get_planner),
) -> StreamingResponse:
    """The same run as `/plan`, narrated to the console as it happens."""
    campaign = get_campaign_or_404(db, campaign_id)
    _require_status(campaign, CampaignStatus.DRAFT, action="planning")

    campaign.status = CampaignStatus.PLANNING
    db.commit()

    brief, source_event = campaign.brief, campaign.source_event
    record = RunLog(campaign, PLAN)

    def work(sink) -> PlanResult:
        return planner.plan(brief, source_event=source_event, sink=record.tee(sink))

    def finish(result: PlanResult) -> dict:
        stored = _store_plan(db, campaign, result)
        _record_plan(db, record, stored)
        return stored.model_dump()

    def recover() -> None:
        campaign.status = CampaignStatus.DRAFT
        db.commit()
        record.failed(db, _last_failure(record) or "Planning failed.")

    return StreamingResponse(
        event_stream(work, finish, on_error=recover),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/concepts/{concept_id}/decision", response_model=ConceptRead)
def decide_concept(
    concept_id: int, payload: ConceptDecision, db: Session = Depends(get_db)
) -> Concept:
    concept = _get_concept(db, concept_id)
    _require_status(
        concept.campaign, CampaignStatus.PENDING_PLAN_APPROVAL, action="a decision"
    )

    concept.status = payload.decision
    concept.edit_note = payload.edit_note
    db.commit()
    return concept


@router.post("/concepts/{concept_id}/revise", response_model=ConceptRead)
def revise_concept(
    concept_id: int,
    payload: ConceptRevision,
    db: Session = Depends(get_db),
    planner: PlanningAgent = Depends(get_planner),
) -> Concept:
    """The gate's edit action: hand the note back to the planner, not an editor."""
    concept = _get_concept(db, concept_id)
    _require_status(
        concept.campaign, CampaignStatus.PENDING_PLAN_APPROVAL, action="an edit"
    )

    try:
        revised = planner.revise(
            concept.campaign.brief,
            to_domain_concept(concept, concept.campaign),
            payload.note,
        )
    except PlanningError as error:
        # The concept the human was looking at is untouched, so they can edit
        # again with a different note or reject it outright.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error

    concept.theme = revised.theme
    concept.format = revised.format
    concept.trend_rationale = revised.trend_rationale
    concept.brand_rationale = revised.brand_rationale
    concept.variant_count = revised.variant_count
    concept.variation_axes = revised.variation_axes
    # Edited, not approved — the point of an edit is that the human looks again.
    concept.status = ConceptStatus.EDITED
    concept.edit_note = payload.note
    db.commit()
    return concept


@router.post("/campaigns/{campaign_id}/approve", response_model=CampaignRead)
def approve_plan(campaign_id: int, db: Session = Depends(get_db)) -> Campaign:
    campaign = get_campaign_or_404(db, campaign_id)
    _require_status(campaign, CampaignStatus.PENDING_PLAN_APPROVAL, action="approval")

    approved = [c for c in campaign.concepts if c.status is ConceptStatus.APPROVED]
    if not approved:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "at least one approved concept is needed before generation",
        )

    campaign.status = CampaignStatus.GENERATING
    db.commit()
    return campaign


def _record_plan(db: Session, record: RunLog, stored: PlanRead) -> None:
    count = len(stored.concepts)
    record.succeeded(
        db,
        f"{count} grounded {'concept' if count == 1 else 'concepts'} proposed",
        concepts=count,
    )


def _last_failure(record: RunLog) -> str | None:
    """The agent's own last words, which say more than "the run failed"."""
    for event in reversed(record.events):
        if event.get("phase") == "failed":
            return str(event.get("detail") or "")
    return None


def _get_concept(db: Session, concept_id: int) -> Concept:
    concept = db.get(Concept, concept_id)
    if concept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no concept {concept_id}")
    return concept


def _require_status(
    campaign: Campaign, expected: CampaignStatus, *, action: str
) -> None:
    if campaign.status is not expected:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"campaign is {campaign.status}, not {expected} — too late for {action}",
        )
