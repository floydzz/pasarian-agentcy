"""Campaign routes, including the plan approval gate.

The gate is the point of the whole design: the planner may propose, but nothing
moves to generation until a human has approved at least one concept. Status
changes happen here and only here, one step at a time.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.planner import PlanningAgent, PlanningError
from app.api.deps import get_planner
from app.api.schemas import (
    CampaignCreate,
    CampaignRead,
    ConceptDecision,
    ConceptRead,
    PlanRead,
)
from app.db import get_db
from app.domain import CampaignStatus, ConceptStatus
from app.models import Campaign, Concept

router = APIRouter(prefix="/api", tags=["campaigns"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
    return _get_campaign(db, campaign_id)


@router.get("/campaigns/{campaign_id}/concepts", response_model=list[ConceptRead])
def list_concepts(campaign_id: int, db: Session = Depends(get_db)) -> list[Concept]:
    _get_campaign(db, campaign_id)
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
    campaign = _get_campaign(db, campaign_id)
    _require_status(campaign, CampaignStatus.DRAFT, action="planning")

    campaign.status = CampaignStatus.PLANNING
    db.flush()

    try:
        result = planner.plan(campaign.brief, source_event=campaign.source_event)
    except PlanningError as error:
        # Planning failed, so the brief is still the thing to fix — hand the
        # campaign back to the human as a draft rather than stranding it.
        campaign.status = CampaignStatus.DRAFT
        db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error

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
    campaign.status = CampaignStatus.PENDING_PLAN_APPROVAL
    db.commit()

    return PlanRead(
        strategy_summary=result.strategy_summary,
        concepts=[ConceptRead.model_validate(concept) for concept in concepts],
    )


@router.post("/concepts/{concept_id}/decision", response_model=ConceptRead)
def decide_concept(
    concept_id: int, payload: ConceptDecision, db: Session = Depends(get_db)
) -> Concept:
    concept = db.get(Concept, concept_id)
    if concept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no concept {concept_id}")

    _require_status(
        concept.campaign, CampaignStatus.PENDING_PLAN_APPROVAL, action="a decision"
    )

    concept.status = payload.decision
    concept.edit_note = payload.edit_note
    db.commit()
    return concept


@router.post("/campaigns/{campaign_id}/approve", response_model=CampaignRead)
def approve_plan(campaign_id: int, db: Session = Depends(get_db)) -> Campaign:
    campaign = _get_campaign(db, campaign_id)
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


def _get_campaign(db: Session, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no campaign {campaign_id}")
    return campaign


def _require_status(
    campaign: Campaign, expected: CampaignStatus, *, action: str
) -> None:
    if campaign.status is not expected:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"campaign is {campaign.status}, not {expected} — too late for {action}",
        )
