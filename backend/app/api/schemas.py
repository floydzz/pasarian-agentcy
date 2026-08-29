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

from app.agents.chat import ChatAction
from app.domain import CampaignStatus, ConceptFormat, ConceptStatus
from app.video.trailer import default_agentcy_trailer_shots


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


class ConversationCreate(BaseModel):
    title: str = Field(default="New strategy", min_length=1, max_length=255)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    #: Setting this to null deliberately detaches a thread. Omitted means
    #: leave its current campaign alone.
    campaign_id: int | None = None

    @field_validator("title")
    @classmethod
    def _optional_title_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=12_000)

    @field_validator("content")
    @classmethod
    def _message_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: Literal["user", "assistant", "system"]
    content: str
    action: ChatAction | None
    created_at: datetime
    updated_at: datetime

    _stamp = field_serializer("created_at", "updated_at")(staticmethod(_utc))


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    campaign_id: int | None
    campaign: CampaignRead | None
    messages: list[ChatMessageRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    _stamp = field_serializer("created_at", "updated_at")(staticmethod(_utc))


class ChatSendRead(BaseModel):
    """The response to a user message, including any safe stream handoff."""

    message: ChatMessageRead
    campaign: CampaignRead | None
    authorized: Literal["plan", "generate"] | None = None


# -- brand profile ----------------------------------------------------------


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


class CreativeRead(BaseModel):
    """One finished creative, with enough context to be read on its own.

    The gallery is browsed away from any campaign, so a creative that arrives
    there carrying only a variant id is a picture of nothing in particular.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    variant_id: int
    media_url: str
    qa_status: str
    qa_notes: str | None
    review_status: str
    created_at: datetime

    campaign_id: int
    campaign_name: str
    concept_theme: str
    headline: str

    _stamp = field_serializer("created_at")(staticmethod(_utc))


class RenderRead(BaseModel):
    """What one render pass did, for the console's result line."""

    variants_rendered: int
    variants_skipped: int
    assets: list[AssetRead]


class AssetDecision(BaseModel):
    """A human's verdict on one creative at the review gate."""

    decision: Literal["approved", "rejected"]


# -- Agentcy product-explainer video --------------------------------------


class DemoVideoCreate(BaseModel):
    """Editable messaging for Agentcy's fixed software-explainer storyboard."""

    title: str = Field(
        default="Marketing should move at the speed of your ideas.",
        min_length=1,
        max_length=280,
    )
    strapline: str = Field(
        default=(
            "Agentcy turns your brand truth and a clear brief into a reviewable "
            "marketing campaign."
        ),
        min_length=1,
        max_length=900,
    )
    cta: str = Field(
        default="Build your next campaign with Agentcy.", min_length=1, max_length=280
    )
    #: Generate moving footage behind every scene. Off by default: the film
    #: renders completely without it, and turning it on spends six paid clips.
    use_broll: bool = False

    @field_validator("title", "strapline", "cta")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class DemoVideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    strapline: str
    cta: str
    media_url: str
    poster_url: str
    duration_seconds: int
    scene_count: int
    qa_status: Literal["passed", "flagged"]
    qa_notes: str | None
    review_status: Literal["pending", "approved", "rejected"]
    created_at: datetime
    updated_at: datetime

    _stamp = field_serializer("created_at", "updated_at")(staticmethod(_utc))


# -- reusable marketing-video studio --------------------------------------


VideoProfile = Literal["software_demo", "product_marketing"]
VideoSceneLayout = Literal["hero", "feature", "workflow", "proof", "cta"]


class MarketingVideoScene(BaseModel):
    eyebrow: str = Field(min_length=1, max_length=80)
    headline: str = Field(min_length=1, max_length=220)
    body: str = Field(min_length=1, max_length=700)
    layout: VideoSceneLayout = "feature"

    @field_validator("eyebrow", "headline", "body")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


def _agentcy_storyboard() -> list[MarketingVideoScene]:
    """The reusable studio opens on the product-demo video the app needs."""
    return [
        MarketingVideoScene(
            eyebrow="Your marketing team, on demand",
            headline="Marketing should move at the speed of your ideas.",
            body="Agentcy turns your brand truth and a clear brief into a reviewable marketing campaign.",
            layout="hero",
        ),
        MarketingVideoScene(
            eyebrow="Start with what is true",
            headline="Set your brand profile.",
            body="Your company, products, claims and guardrails ground every agent before work begins.",
            layout="feature",
        ),
        MarketingVideoScene(
            eyebrow="One connected workflow",
            headline="Brief it. Make it. Review it.",
            body="The planner, copywriter, visual planner and director move the campaign forward together.",
            layout="workflow",
        ),
        MarketingVideoScene(
            eyebrow="Keep the decision",
            headline="Review before anything leaves.",
            body="Vision QA checks the creative first. Your team decides what is approved, redone or rejected.",
            layout="proof",
        ),
        MarketingVideoScene(
            eyebrow="Make the next campaign",
            headline="From clear brief to work worth sharing.",
            body="Grounded strategy, reviewable creative and a workflow your team can actually run.",
            layout="cta",
        ),
    ]


class MarketingVideoCreate(BaseModel):
    """A durable video brief, defaulted to Agentcy's software-demo preset."""

    name: str = Field(default="Agentcy software explainer", min_length=1, max_length=280)
    profile: VideoProfile = "software_demo"
    brand_name: str = Field(default="Agentcy", min_length=1, max_length=200)
    product_name: str = Field(
        default="AI marketing campaign workspace", min_length=1, max_length=280
    )
    target_audience: str = Field(
        default="Marketing teams who need a grounded, reviewable campaign workflow.",
        min_length=1,
        max_length=700,
    )
    cta: str = Field(
        default="Build your next campaign with Agentcy.", min_length=1, max_length=280
    )
    storyboard: list[MarketingVideoScene] = Field(
        default_factory=_agentcy_storyboard, min_length=3, max_length=8
    )
    #: Opt-in generative backdrops. Off by default: a clip costs money and
    #: about a minute and a half per scene, while the deterministic render is
    #: instant and free. Ignored when no video provider is configured.
    use_broll: bool = False
    #: Campaign video renders can select a photo to lock into the local frame.
    product_reference_id: int | None = None

    @field_validator("name", "brand_name", "product_name", "target_audience", "cta")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class MarketingVideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int | None
    name: str
    profile: VideoProfile
    brand_name: str
    product_name: str
    target_audience: str
    cta: str
    storyboard: list[MarketingVideoScene]
    product_reference_url: str | None
    media_url: str
    poster_url: str
    duration_seconds: int
    scene_count: int
    qa_status: Literal["passed", "flagged"]
    qa_notes: str | None
    review_status: Literal["pending", "approved", "rejected"]
    created_at: datetime
    updated_at: datetime

    _stamp = field_serializer("created_at", "updated_at")(staticmethod(_utc))


# -- cinematic trailers ----------------------------------------------------


CinematicShotMode = Literal["text_to_video", "image_to_video", "reference_to_video"]
CinematicShotStatus = Literal["draft", "pending", "running", "succeeded", "failed"]
CinematicTrailerStatus = Literal["draft", "generating", "ready_to_compose", "rendered", "failed"]
CinematicProductSurface = Literal["none", "studio", "hub", "history"]


class CinematicTrailerShotCreate(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    title_card: str = Field(min_length=1, max_length=280)
    prompt: str = Field(min_length=1, max_length=5000)
    mode: CinematicShotMode = "text_to_video"
    duration_seconds: int = Field(ge=3, le=15)
    voiceover: str = Field(min_length=1, max_length=2000)
    audio_cue: str = Field(min_length=1, max_length=1000)
    reference_asset_urls: list[str] = Field(default_factory=list, max_length=4)
    protect_reference: bool = False
    product_surface: CinematicProductSurface = "none"
    #: Used only by the built-in Agentcy trailer preset. The API resolves the
    #: checked-in product screenshot to a normal `/media/…` asset on creation.
    use_application_image: bool = False

    @field_validator("label", "title_card", "prompt", "voiceover", "audio_cue")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class CinematicTrailerCreate(BaseModel):
    campaign_id: int | None = None
    title: str = Field(default="Agentcy — The Network Woke Up", min_length=1, max_length=280)
    aspect_ratio: Literal["16:9", "9:16"] = "16:9"
    cta: str = Field(default="BUILD YOUR NEXT CAMPAIGN", min_length=1, max_length=280)
    shots: list[CinematicTrailerShotCreate] = Field(
        default_factory=lambda: [
            CinematicTrailerShotCreate.model_validate(shot)
            for shot in default_agentcy_trailer_shots()
        ],
        min_length=3,
        max_length=24,
    )

    @field_validator("title", "cta")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class CinematicTrailerShotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    label: str
    title_card: str
    prompt: str
    mode: CinematicShotMode
    duration_seconds: int
    voiceover: str
    audio_cue: str
    reference_asset_urls: list[str]
    protect_reference: bool
    product_surface: CinematicProductSurface
    remote_task_id: str | None
    provider_status: CinematicShotStatus
    provider_error: str | None
    media_url: str | None


class CinematicTrailerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int | None
    title: str
    aspect_ratio: Literal["16:9", "9:16"]
    cta: str
    status: CinematicTrailerStatus
    media_url: str | None
    poster_url: str | None
    application_capture_url: str | None
    soundtrack_url: str | None
    product_reference_url: str | None
    duration_seconds: int
    review_status: Literal["pending", "approved", "rejected"]
    shots: list[CinematicTrailerShotRead]
    created_at: datetime
    updated_at: datetime

    _stamp = field_serializer("created_at", "updated_at")(staticmethod(_utc))


class CinematicTrailerAssetCreate(BaseModel):
    """A browser-uploaded screenshot as a data URL.

    JSON keeps this route simple and lets the server validate bytes before it
    hands anything to an external generation model.
    """

    data_url: str = Field(min_length=32, max_length=30_000_000)


class CinematicTrailerCaptureCreate(BaseModel):
    """A recorded, real product interaction for screen replacement.

    Captures are deliberately separate from reference images. Feature-shot
    generation receives only the corresponding still frame extracted from the
    recording; it is not pasted over the resulting AI clip.
    """

    # A syntactically valid, tiny MP4 can be shorter than 64 characters once
    # base64-encoded. Byte-level validation below remains the authority.
    data_url: str = Field(min_length=32, max_length=180_000_000)


class CinematicTrailerSoundtrackCreate(BaseModel):
    """A real instrumental track for the final trailer mix.

    Music generation is configured separately from video generation, so this
    route also supports a licensed or otherwise already-generated MP3/WAV.
    The composer loops and ducks it beneath the AI clips deterministically.
    """

    data_url: str = Field(min_length=32, max_length=80_000_000)


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
    max_redos: int | None = None
    context_turns: int | None = None


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
