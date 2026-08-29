"""Request and response bodies for the campaign API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)

from app.domain import CampaignStatus, ConceptFormat, ConceptStatus


def _utc(value: datetime | None) -> datetime | None:
    """Say that a stored timestamp is UTC, because the column cannot.

    MySQL `DATETIME` carries no zone and `app.clock` writes UTC into it. Sent
    on unmarked, an ISO string with no offset is parsed by a browser as *local*
    time — so a row written a second ago on a UTC container renders as eight
    hours old in Kuala Lumpur. Stamping the zone here is the other half of that
    contract.
    """
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


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
    auto_approve_plan: bool
    auto_approve_assets: bool
    created_at: datetime
    updated_at: datetime

    _stamp = field_serializer("created_at", "updated_at")(staticmethod(_utc))


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


class ConceptRevision(BaseModel):
    """The chat handoff behind the gate's edit action.

    A note, not an edited concept: the human says what should change and the
    planner reworks the idea against the knowledge base, so an edit cannot
    smuggle in an ungrounded claim the way a free-text editor would.
    """

    note: str = Field(min_length=1)

    @field_validator("note")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class AutoModeUpdate(BaseModel):
    """The auto-mode toggles. Omitted fields are left as they are.

    Both gates take the same shape deliberately — one human-in-the-loop
    pattern, set the same way, so the UI has one control to render twice.
    """

    auto_approve_plan: bool | None = None
    auto_approve_assets: bool | None = None


class VariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    concept_id: int
    hook_type: str
    headline: str
    body: str
    cta: str
    visual_brief: dict
    director_status: str
    director_notes: str | None
    revision_count: int


class GenerationRead(BaseModel):
    """What came back from running the crew across a campaign's concepts."""

    concepts_generated: int
    concepts_skipped: int
    variants: list[VariantRead]

    @property
    def flagged(self) -> int:
        return sum(1 for v in self.variants if v.director_status == "flagged")


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    variant_id: int
    media_url: str
    qa_status: str
    qa_notes: str | None
    review_status: str


class RenderRead(BaseModel):
    """What one render pass did, for the console's result line."""

    variants_rendered: int
    variants_skipped: int
    assets: list[AssetRead]


class AssetDecision(BaseModel):
    """A human's verdict on one creative at the review gate."""

    decision: Literal["approved", "rejected"]


# -- agent tuning ----------------------------------------------------------


class KnobRead(BaseModel):
    """One integer setting, with the range the console may offer for it."""

    field: str
    label: str
    help: str
    minimum: int
    maximum: int
    default: int
    value: int


class AgentRead(BaseModel):
    """An agent as the settings screen sees it: what it does, what it may not
    do, and the few numbers a person is allowed to move."""

    agent: str
    label: str
    role: str
    boundary: str
    note_placeholder: str
    standing_note: str | None
    knobs: list[KnobRead]
    #: True when nothing has been changed from the shipped defaults.
    is_default: bool


class AgentUpdate(BaseModel):
    """Omitted fields are left alone; `standing_note: ""` clears the note.

    Values are clamped to each knob's declared range rather than rejected —
    the range belongs to the machine, so the end of a slider is a valid place
    to stop.
    """

    standing_note: str | None = None
    concept_count: int | None = None
    company_k: int | None = None
    trend_k: int | None = None
    max_revisions: int | None = None


# -- history ---------------------------------------------------------------


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int | None
    campaign_name: str
    kind: str
    status: str
    started_at: datetime
    duration_ms: int
    summary: str
    error: str | None
    concepts: int
    variants: int
    flagged: int
    revisions: int
    provider: str

    _stamp = field_serializer("started_at")(staticmethod(_utc))


class RunDetail(RunRead):
    """One run with its events — what the console showed while it ran."""

    events: list[dict]


# -- trend scraping --------------------------------------------------------


class TrendSignalRead(BaseModel):
    query: str
    value: int
    rising: bool


class TrendSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keyword: str
    geo: str
    enabled: bool
    note: str | None
    last_scraped_at: datetime | None
    last_mode: str
    last_error: str | None
    last_signals: list[TrendSignalRead]

    _stamp = field_serializer("last_scraped_at")(staticmethod(_utc))


class TrendSourceCreate(BaseModel):
    keyword: str = Field(min_length=1, max_length=200)
    geo: str = Field(default="MY", min_length=2, max_length=8)
    note: str | None = None

    @field_validator("keyword")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class TrendSourceUpdate(BaseModel):
    keyword: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = None
    enabled: bool | None = None


class ScrapeRead(BaseModel):
    """The outcome of one keyword in a scrape pass."""

    source_id: int
    keyword: str
    mode: str
    chunks: int
    signals: list[TrendSignalRead]
    error: str | None


class CorpusSourceRead(BaseModel):
    source: str
    chunks: int
    heading: str


class TrendStatusRead(BaseModel):
    """Whether the scraper has a live source, and what the corpus holds.

    `live` is stated plainly because it changes what the numbers below mean:
    offline samples ingest exactly like measured signals, so the only place the
    difference can be shown is here.
    """

    live: bool
    geo: str
    trend_chunks: int
    company_chunks: int
    documents: list[CorpusSourceRead]


class ProductReferenceCreate(BaseModel):
    """A campaign product photo uploaded as a browser data URL."""

    label: str = Field(default="Product image", min_length=1, max_length=200)
    data_url: str = Field(min_length=32, max_length=30_000_000)
    is_primary: bool = False

    @field_validator("label")
    @classmethod
    def _label_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ProductReferencePatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    is_primary: bool | None = None

    @field_validator("label")
    @classmethod
    def _optional_label_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ProductReferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    label: str
    media_url: str
    is_primary: bool
    created_at: datetime
    updated_at: datetime

    _stamp = field_serializer("created_at", "updated_at")(staticmethod(_utc))


# -- marketing chat -------------------------------------------------------


class BrandProduct(BaseModel):
    """One offer the agents may describe, but never embellish."""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    price: str | None = Field(default=None, max_length=120)
    benefits: str | None = Field(default=None, max_length=1000)

    @field_validator("name", "description")
    @classmethod
    def _required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("price", "benefits")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class BrandProfileWrite(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    industry: str = Field(min_length=1, max_length=120)
    website: str | None = Field(default=None, max_length=500)
    description: str = Field(min_length=1, max_length=4000)
    brand_voice: str = Field(min_length=1, max_length=2000)
    target_audience: str = Field(min_length=1, max_length=2000)
    products: list[BrandProduct] = Field(min_length=1, max_length=20)
    approved_claims: str | None = Field(default=None, max_length=2000)
    restrictions: str | None = Field(default=None, max_length=2000)

    @field_validator(
        "company_name", "industry", "description", "brand_voice", "target_audience"
    )
    @classmethod
    def _required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("website", "approved_claims", "restrictions")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class BrandProfileRead(BaseModel):
    configured: bool
    knowledge_chunks: int
    company_name: str
    industry: str
    website: str | None
    description: str
    brand_voice: str
    target_audience: str
    products: list[BrandProduct]
    approved_claims: str | None
    restrictions: str | None
    updated_at: datetime | None = None

    _stamp = field_serializer("updated_at")(staticmethod(_utc))
