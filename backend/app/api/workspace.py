"""Small dashboard summaries, paginated directories and measured outcomes."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_campaign_or_404
from app.api.schemas import CampaignRead
from app.db import get_db
from app.domain import CampaignStatus
from app.marketing_calendar import as_dict, attention
from app.models import Campaign, CampaignResult, MarketingPlan, Workspace, Job
from app.workspace import principal

router = APIRouter(prefix="/api", tags=["workspace"])


@router.get("/campaign-directory")
def campaign_directory(q: str = Query(default="", max_length=200), status: str = "all", offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    query = select(Campaign)
    if q.strip():
        # Literal search; SQL wildcards typed by a user are not wildcards.
        value = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(or_(Campaign.name.ilike(f"%{value}%", escape="\\"), Campaign.brief.ilike(f"%{value}%", escape="\\"), Campaign.source_event.ilike(f"%{value}%", escape="\\")))
    groups = {"review": ["pending_plan_approval", "pending_asset_review"], "working": ["planning", "generating"], "ready": ["ready_to_publish", "published"], "draft": ["draft"]}
    if status != "all":
        if status not in groups:
            raise HTTPException(422, "Unknown campaign filter")
        query = query.where(Campaign.status.in_(groups[status]))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Campaign.updated_at.desc(), Campaign.id.desc()).offset(offset).limit(limit))
    return {"items": [CampaignRead.model_validate(row).model_dump(mode="json") for row in rows], "total": total, "offset": offset, "limit": limit}


@router.get("/workspace/overview")
def overview(db: Session = Depends(get_db)):
    counts = {str(key): count for key, count in db.execute(select(Campaign.status, func.count(Campaign.id)).group_by(Campaign.status))}
    review = list(db.scalars(select(Campaign).where(Campaign.status.in_(["pending_plan_approval", "pending_asset_review"])).order_by(Campaign.updated_at).limit(4)))
    recent = list(db.scalars(select(Campaign).order_by(Campaign.updated_at.desc(), Campaign.id.desc()).limit(4)))
    return {"active_jobs": db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(["queued", "running"]))), "counts": counts, "needs_review": [CampaignRead.model_validate(row).model_dump(mode="json") for row in review],
            "recent": [CampaignRead.model_validate(row).model_dump(mode="json") for row in recent], "attention": attention(db)[:8],
            "active_plans": db.scalar(select(func.count()).select_from(MarketingPlan).where(MarketingPlan.status != "archived"))}


class ResultWrite(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    channel: str = Field(min_length=1, max_length=40)
    period_start: date
    period_end: date
    spend: float = Field(default=0, ge=0, le=1_000_000_000)
    revenue: float = Field(default=0, ge=0, le=1_000_000_000)
    impressions: int = Field(default=0, ge=0, le=2_000_000_000)
    engagements: int = Field(default=0, ge=0, le=2_000_000_000)
    leads: int = Field(default=0, ge=0, le=2_000_000_000)
    sales: int = Field(default=0, ge=0, le=2_000_000_000)
    currency: Literal["MYR", "USD"] = "MYR"
    notes: str = Field(default="", max_length=2000)
    version: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def dates(self):
        self.channel = self.channel.strip().lower()
        if not self.channel or self.period_end < self.period_start:
            raise ValueError("Enter a channel and a valid reporting period")
        return self


@router.get("/campaigns/{campaign_id}/results")
def results(campaign_id: int, db: Session = Depends(get_db)):
    get_campaign_or_404(db, campaign_id)
    return [as_dict(row) for row in db.scalars(select(CampaignResult).where(CampaignResult.campaign_id == campaign_id).order_by(CampaignResult.period_end.desc()).limit(100))]


@router.post("/campaigns/{campaign_id}/results")
def save_result(campaign_id: int, payload: ResultWrite, db: Session = Depends(get_db)):
    if db.scalar(select(Campaign.id).where(Campaign.id == campaign_id).with_for_update()) is None:
        raise HTTPException(404, "Campaign not found")
    row = db.scalar(select(CampaignResult).where(CampaignResult.campaign_id == campaign_id, CampaignResult.channel == payload.channel,
                    CampaignResult.period_start == payload.period_start, CampaignResult.period_end == payload.period_end).with_for_update())
    if row and row.version != payload.version or not row and payload.version != 0:
        raise HTTPException(409, "Results changed in another tab. Reload before saving.")
    # Overlapping periods would silently double-count marketing performance.
    overlap = select(CampaignResult.id).where(CampaignResult.campaign_id == campaign_id, CampaignResult.channel == payload.channel,
        CampaignResult.period_start <= payload.period_end, CampaignResult.period_end >= payload.period_start)
    if row:
        overlap = overlap.where(CampaignResult.id != row.id)
    if db.scalar(overlap.limit(1)):
        raise HTTPException(409, "This channel already has results for an overlapping period")
    if row is None:
        row = CampaignResult(campaign_id=campaign_id, **payload.model_dump(exclude={"version"})); db.add(row); row.version = 1
    else:
        for key, value in payload.model_dump(exclude={"version"}).items():
            setattr(row, key, value)
        row.version += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "Results changed in another tab. Reload before saving.")
    return as_dict(row)


class BudgetWrite(BaseModel):
    token_limit_per_job: int = Field(ge=1000, le=2_000_000)
    call_limit_per_job: int = Field(ge=1, le=1000)
    max_llm_cost_per_job: float | None = Field(default=None, gt=0, le=10000, allow_inf_nan=False)
    llm_prices: dict[str, tuple[float, float]] = Field(default_factory=dict, max_length=30)

    @model_validator(mode="after")
    def prices(self):
        import math
        if any(not model.strip() or len(model) > 120 or any(not math.isfinite(rate) or rate < 0 or rate > 10000 for rate in rates) for model, rates in self.llm_prices.items()):
            raise ValueError("Enter valid model prices in USD per million input/output tokens")
        return self


@router.get("/workspace/budgets")
def budgets(db: Session = Depends(get_db)):
    row = db.get(Workspace, principal.get().workspace_id)
    return {"token_limit_per_job": row.token_limit_per_job, "call_limit_per_job": row.call_limit_per_job, "max_llm_cost_per_job": row.max_llm_cost_per_job, "llm_prices": row.llm_prices}


@router.put("/workspace/budgets")
def update_budgets(payload: BudgetWrite, db: Session = Depends(get_db)):
    row = db.get(Workspace, principal.get().workspace_id)
    row.token_limit_per_job, row.call_limit_per_job = payload.token_limit_per_job, payload.call_limit_per_job
    row.max_llm_cost_per_job, row.llm_prices = payload.max_llm_cost_per_job, payload.llm_prices
    db.commit(); return budgets(db)
