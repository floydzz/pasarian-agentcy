"""Core domain schemas shared by the API, the agents and the persistence layer.

These mirror the JSON contracts in the implementation plan. Every LLM call in the
system is constrained to one of these shapes — nothing between agents is parsed
out of free text.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    PLANNING = "planning"
    PENDING_PLAN_APPROVAL = "pending_plan_approval"
    GENERATING = "generating"
    PENDING_ASSET_REVIEW = "pending_asset_review"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHED = "published"


#: The one legal path through a campaign. Kept as an explicit ordering so the
#: gates can't be skipped by a stray status write.
CAMPAIGN_FLOW: tuple[CampaignStatus, ...] = (
    CampaignStatus.DRAFT,
    CampaignStatus.PLANNING,
    CampaignStatus.PENDING_PLAN_APPROVAL,
    CampaignStatus.GENERATING,
    CampaignStatus.PENDING_ASSET_REVIEW,
    CampaignStatus.READY_TO_PUBLISH,
    CampaignStatus.PUBLISHED,
)


def next_status(current: CampaignStatus) -> CampaignStatus | None:
    """The status that follows `current`, or None if the campaign is published."""
    index = CAMPAIGN_FLOW.index(current)
    if index + 1 == len(CAMPAIGN_FLOW):
        return None
    return CAMPAIGN_FLOW[index + 1]


def can_transition(current: CampaignStatus, target: CampaignStatus) -> bool:
    """Campaigns only ever move forward, one stage at a time."""
    return next_status(current) == target


class ConceptStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


ConceptFormat = Literal["image", "video", "carousel"]


class Concept(BaseModel):
    """Planning agent output. One campaign idea, plus its diversity strategy."""

    concept_id: str
    theme: str
    format: ConceptFormat
    trend_rationale: str = Field(description="Cites a specific trend corpus chunk")
    brand_rationale: str = Field(description="Cites a specific company KB chunk")
    variant_count: int = Field(ge=1, le=6)
    variation_axes: list[str] = Field(min_length=1, max_length=6)
    status: ConceptStatus = ConceptStatus.PENDING
    #: Set when the concept came from the calendar scheduler rather than a human
    #: brief, e.g. "suggested: Hari Raya, 18 days out". Stretch feature.
    provenance: str | None = None

    @model_validator(mode="after")
    def _axes_cover_every_variant(self) -> Concept:
        if self.variant_count != len(self.variation_axes):
            raise ValueError(
                "variant_count must equal the number of variation_axes — each "
                f"variant executes exactly one axis (got {self.variant_count} "
                f"variants for {len(self.variation_axes)} variation_axes)"
            )
        return self


#: Where composited text sits. A nine-cell grid rather than free text, because
#: the compositor lays out against it — prose cannot drive a layout engine.
PlacementZone = Literal[
    "top-left", "top-center", "top-right",
    "mid-left", "mid-center", "mid-right",
    "bottom-left", "bottom-center", "bottom-right",
]

#: How the compositor protects the copy after the image model has rendered the
#: background.  This is a creative decision made by the visual planner, rather
#: than a global UI decoration applied to every asset.
TextTreatment = Literal["bare", "soft-gradient", "glass-panel", "ribbon"]


class VisualBrief(BaseModel):
    composition_notes: str
    image_prompt: str
    #: Prose, and it stays prose: this is what steers the image prompt toward
    #: leaving usable negative space, which no enum expresses.
    text_placement: str
    #: The same intent as `text_placement`, in the one form Pillow can act on.
    placement_zone: PlacementZone
    #: The visual planner's copy-surface decision.  Existing briefs pre-date
    #: this field, so they retain the old readable glass panel on rerender.
    text_treatment: TextTreatment = "glass-panel"


class Variant(BaseModel):
    """Copywriter + visual planner output, reviewed by the director agent."""

    variant_id: str
    concept_id: str
    hook_type: str = Field(description="Which variation axis this variant executes")
    headline: str
    body: str
    cta: str
    visual_brief: VisualBrief
    #: Starts flagged: a variant is only "pass" once the director has said so.
    director_status: Literal["pass", "flagged"] = "flagged"
    director_notes: str | None = None


class Asset(BaseModel):
    """A generated creative, pre-screened by vision QA before a human sees it."""

    asset_id: str
    variant_id: str
    media_url: str
    #: Same principle as director_status — nothing is "passed" until QA runs.
    qa_status: Literal["passed", "flagged"] = "flagged"
    qa_notes: str | None = None
    review_status: Literal["pending", "approved", "rejected"] = "pending"


class CalendarEvent(BaseModel):
    """Seed data for the proactive recommendation scheduler (stretch feature)."""

    event_id: str
    name: str
    date: date
    lookahead_days: int = Field(ge=1, le=90)
    suggested_tone: str
