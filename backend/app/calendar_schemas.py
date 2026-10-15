"""Typed calendar contracts shared by HTTP, chat and AI validation."""
from __future__ import annotations
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

STATES = {
    "JHR": "Johor", "KDH": "Kedah", "KTN": "Kelantan", "MLK": "Melaka",
    "NSN": "Negeri Sembilan", "PHG": "Pahang", "PRK": "Perak", "PLS": "Perlis",
    "PNG": "Pulau Pinang", "SBH": "Sabah", "SWK": "Sarawak", "SGR": "Selangor",
    "TRG": "Terengganu", "KUL": "Kuala Lumpur", "LBN": "Labuan", "PJY": "Putrajaya",
}

class Contract(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True, extra="forbid")

class DateRange(Contract):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_date < self.start_date or (self.end_date - self.start_date).days > 400:
            raise ValueError("Choose an ordered date range of at most 400 days")
        return self

class Preferences(Contract):
    states: list[str] = Field(default_factory=lambda: ["SGR"], max_length=16)
    goals: str = Field(default="", max_length=2000)
    annual_budget: float | None = Field(default=None, ge=0, le=1_000_000_000, allow_inf_nan=False)
    campaigns_per_month: int = Field(default=2, ge=1, le=10)
    lead_days: int = Field(default=28, ge=1, le=90)
    reminder_days: int = Field(default=7, ge=1, le=30)
    blackout_dates: list[date] = Field(default_factory=list, max_length=100)
    version: int = Field(default=0, ge=0)

    @field_validator("states")
    @classmethod
    def state_codes(cls, values):
        if not values or any(value not in STATES for value in values):
            raise ValueError("Choose at least one valid Malaysian state")
        return list(dict.fromkeys(values))

class BusinessEventWrite(DateRange):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    archived: bool = False

class BusinessEventPatch(BusinessEventWrite):
    version: int = Field(ge=1)

class PlanWrite(DateRange):
    name: str = Field(min_length=1, max_length=200)
    goals: str = Field(default="", max_length=2000)

class PlanPatch(PlanWrite):
    version: int = Field(ge=1)
    status: Literal["draft", "accepted", "archived"] = "draft"

class TaskProposal(Contract):
    title: str = Field(min_length=1, max_length=200)
    due_date: date

class ItemProposal(Contract):
    occasion_id: int | None = None
    business_event_id: int | None = None
    title: str = Field(min_length=1, max_length=200)
    rationale: str = Field(default="", max_length=2000)
    strategy: str = Field(min_length=1, max_length=4000)
    audience: str = Field(default="", max_length=2000)
    products: list[str] = Field(default_factory=list, max_length=20)
    offer: str = Field(default="", max_length=1000)
    budget: float | None = Field(default=None, ge=0, le=1_000_000_000, allow_inf_nan=False)
    campaign_start: date
    campaign_end: date
    preparation_start: date
    tasks: list[TaskProposal] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def dates(self):
        if self.campaign_end < self.campaign_start or self.preparation_start > self.campaign_start:
            raise ValueError("Preparation must start before the ordered campaign period")
        if (self.campaign_end - self.campaign_start).days > 90:
            raise ValueError("A single campaign may span at most 90 days")
        if self.occasion_id is not None and self.business_event_id is not None:
            raise ValueError("Choose one occasion or business event")
        return self

class ItemWrite(ItemProposal):
    status: Literal["proposed", "planned", "skipped", "cancelled"] = "proposed"

class ItemPatch(ItemWrite):
    version: int = Field(ge=1)

class CalendarProposal(Contract):
    summary: str = Field(min_length=1, max_length=4000)
    items: list[ItemProposal] = Field(min_length=1, max_length=24)
    assumptions: list[str] = Field(default_factory=list, max_length=20)

class RunRequest(DateRange):
    states: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("states")
    @classmethod
    def valid_states(cls, states):
        if any(state not in STATES for state in states):
            raise ValueError("Unknown Malaysian state")
        return list(dict.fromkeys(states))

    operation: Literal["annual", "item"] = "annual"
    plan_id: int | None = None
    item_id: int | None = None
    occasion_id: int | None = None
    business_event_id: int | None = None
    instructions: str = Field(default="", max_length=4000)
    request_key: str = Field(min_length=8, max_length=80)

    @model_validator(mode="after")
    def scope(self):
        if self.operation == "item" and not any((self.item_id, self.occasion_id, self.business_event_id)):
            raise ValueError("Select an occasion, business event or plan item")
        if self.occasion_id and self.business_event_id:
            raise ValueError("Choose one occasion or business event")
        return self

class AcceptRequest(Contract):
    name: str = Field(default="Marketing roadmap", min_length=1, max_length=200)
    expected_version: int | None = None

class VersionRequest(Contract):
    version: int = Field(ge=1)

class TaskPatch(VersionRequest):
    status: Literal["todo", "done"]
    due_date: date

class DismissRequest(Contract):
    key: str = Field(min_length=1, max_length=200)
    until: date
