"""Request and response bodies for the campaign API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain import CampaignStatus, ConceptFormat, ConceptStatus


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    brief: str = Field(min_length=1)
    source_event: str | None = None

    @field_validator("name", "brief")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class CampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    brief: str
    status: CampaignStatus
    source_event: str | None
    created_at: datetime
    updated_at: datetime


class ConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    theme: str
    format: ConceptFormat
    trend_rationale: str
    brand_rationale: str
    variant_count: int
    variation_axes: list[str]
    status: ConceptStatus
    edit_note: str | None


class PlanRead(BaseModel):
    strategy_summary: str
    concepts: list[ConceptRead]


class ConceptDecision(BaseModel):
    """A human's verdict at the plan approval gate."""

    decision: Literal[ConceptStatus.APPROVED, ConceptStatus.REJECTED, ConceptStatus.EDITED]
    edit_note: str | None = None
