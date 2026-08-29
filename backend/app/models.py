"""ORM models for the campaign pipeline: campaigns → concepts → variants → assets."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .domain import CampaignStatus, ConceptStatus


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Campaign(TimestampMixin, Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brief: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, native_enum=False, length=32),
        default=CampaignStatus.DRAFT,
        nullable=False,
    )
    #: Set when the calendar scheduler drafted this brief instead of a human.
    #: Stretch feature; the column exists now so the gates can show provenance.
    source_event: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Auto-mode is per-gate but behaves identically at both — see the plan's
    # non-functional requirements.
    auto_approve_plan: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    auto_approve_assets: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    concepts: Mapped[list["Concept"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    #: A conversation can outlive its campaign. The database clears the
    #: association when a campaign is removed, leaving the strategy history.
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="campaign", passive_deletes=True
    )
    product_references: Mapped[list["ProductReference"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ProductReference(TimestampMixin, Base):
    """A real product image a campaign may keep intact in its creative."""

    __tablename__ = "product_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    media_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    #: One primary photo is selected for product-lock composition.
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    campaign: Mapped[Campaign] = relationship(back_populates="product_references")


class Concept(TimestampMixin, Base):
    __tablename__ = "concepts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    theme: Mapped[str] = mapped_column(String(500), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    trend_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    brand_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    variant_count: Mapped[int] = mapped_column(Integer, nullable=False)
    variation_axes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[ConceptStatus] = mapped_column(
        Enum(ConceptStatus, native_enum=False, length=20),
        default=ConceptStatus.PENDING,
        nullable=False,
    )
    #: Free-text note from the approval gate's chat handoff when a human edits.
    edit_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    campaign: Mapped[Campaign] = relationship(back_populates="concepts")
    variants: Mapped[list["Variant"]] = relationship(
        back_populates="concept",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Variant(TimestampMixin, Base):
    __tablename__ = "variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hook_type: Mapped[str] = mapped_column(String(255), nullable=False)
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cta: Mapped[str] = mapped_column(String(255), nullable=False)
    visual_brief: Mapped[dict] = mapped_column(JSON, nullable=False)
    director_status: Mapped[str] = mapped_column(
        String(20), default="flagged", nullable=False
    )
    director_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Bounded revision counter — the director loop stops at 2 (see the plan).
    revision_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    concept: Mapped[Concept] = relationship(back_populates="variants")
    assets: Mapped[list["Asset"]] = relationship(
        back_populates="variant",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    qa_status: Mapped[str] = mapped_column(
        String(20), default="flagged", nullable=False
    )
    qa_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )

    variant: Mapped[Variant] = relationship(back_populates="assets")


class AgentSetting(TimestampMixin, Base):
    """How one agent is tuned, kept out of the environment on purpose.

    These are creative-direction knobs, not deployment config: how many concepts
    to propose, how much of the brand to read before writing, how many times the
    director may send work back. A marketer changes them between campaigns, so
    they live in the database where a person can reach them, and every column is
    nullable because no agent uses all of them.
    """

    __tablename__ = "agent_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)

    #: Appended to the agent's system prompt as a standing house rule. Additive
    #: only — it cannot delete the grounding rules the prompt already states.
    standing_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Company-knowledge chunks retrieved before this agent works.
    company_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Trend chunks retrieved. Planner only — nobody else is allowed trends.
    trend_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Concepts the planner proposes per brief.
    concept_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Times the director may send work back before it falls through flagged.
    max_revisions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Times vision QA may send a creative back to be re-rendered.
    max_redos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Number of recent turns the marketing strategist reads before replying.
    context_turns: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Conversation(TimestampMixin, Base):
    """A named, durable conversation with the marketing strategist.

    A thread starts unbound. Once the strategist has enough of a brief to
    create a campaign, it adopts that campaign; deleting the campaign later
    only clears this pointer, so the conversation remains useful history.
    """

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True
    )

    campaign: Mapped[Campaign | None] = relationship(back_populates="conversations")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ChatMessage(TimestampMixin, Base):
    """One user, strategist, or machine line inside a conversation."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: String rather than a database enum: roles are presentation categories
    #: and a future migration can add one without changing deployed MySQL enum
    #: values.
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    #: The action the strategist proposed, if any. This is an audit trail;
    #: the executor still validates current campaign state before it acts.
    action: Mapped[str | None] = mapped_column(String(32), nullable=True)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class BrandProfile(TimestampMixin, Base):
    """The single workspace's source of truth about its company.

    Authentication and organisations are deliberately not in this MVP, so one
    profile belongs to the one workspace.  The API turns this row into the only
    document in the company corpus whenever a person saves it.
    """

    __tablename__ = "brand_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str] = mapped_column(String(120), nullable=False)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    brand_voice: Mapped[str] = mapped_column(Text, nullable=False)
    target_audience: Mapped[str] = mapped_column(Text, nullable=False)
    products: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    approved_claims: Mapped[str | None] = mapped_column(Text, nullable=True)
    restrictions: Mapped[str | None] = mapped_column(Text, nullable=True)


class DemoVideo(TimestampMixin, Base):
    """One rendered Agentcy product-explainer waiting for, or past, review.

    This stays separate from customer campaign assets.  Its subject is Agentcy
    itself, its storyboard is fixed product UI, and it has its own export gate.
    """

    __tablename__ = "demo_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(280), nullable=False)
    strapline: Mapped[str] = mapped_column(Text, nullable=False)
    cta: Mapped[str] = mapped_column(String(280), nullable=False)
    media_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    poster_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_count: Mapped[int] = mapped_column(Integer, nullable=False)
    qa_status: Mapped[str] = mapped_column(
        String(20), default="flagged", nullable=False
    )
    qa_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )


class MarketingVideo(TimestampMixin, Base):
    """A configurable marketing video made from a persisted storyboard.

    `DemoVideo` preserves the initial fixed Agentcy film. New work belongs in
    this table: its generic title is intentional, and each row carries all
    configuration needed to reproduce it later at the review gate.

    `campaign_id` is nullable because a video does not need a campaign to
    exist — the product explainer and any one-off film have none — but a video
    made inside a campaign's video studio belongs to it and dies with it.
    """

    __tablename__ = "marketing_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(280), nullable=False)
    profile: Mapped[str] = mapped_column(String(40), nullable=False)
    brand_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_name: Mapped[str] = mapped_column(String(280), nullable=False)
    target_audience: Mapped[str] = mapped_column(Text, nullable=False)
    cta: Mapped[str] = mapped_column(String(280), nullable=False)
    storyboard: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    #: Whether this video was rendered over generated b-roll. Saved with the
    #: brief so a redo reproduces the same video rather than quietly dropping
    #: back to the deterministic render.
    use_broll: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Persist the photo actually used so redos cannot drift to a newer image.
    product_reference_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    media_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    poster_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_count: Mapped[int] = mapped_column(Integer, nullable=False)
    qa_status: Mapped[str] = mapped_column(
        String(20), default="flagged", nullable=False
    )
    qa_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )


class CinematicTrailer(TimestampMixin, Base):
    """A long-form, AI-shot product film.

    Shot jobs live in their own table rather than a JSON blob: each external
    task can be submitted, polled, retried and downloaded independently while
    the rest of a two-minute render keeps its work.
    """

    __tablename__ = "cinematic_trailers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: A cinematic project may stand on its own, but work created from a
    #: campaign's storyboard stays attached to that campaign so Video Studio
    #: can show only the clips that belong to the script being reviewed.
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(280), nullable=False)
    aspect_ratio: Mapped[str] = mapped_column(String(12), default="16:9", nullable=False)
    cta: Mapped[str] = mapped_column(String(280), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    media_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    poster_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # A real browser-recorded product journey. Feature-shot generation receives
    # only an extracted still of the relevant timestamp, never the full
    # recording. Legacy protected shots may still use it locally.
    application_capture_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    #: An optional licensed or AI-generated instrumental mixed beneath the
    #: finished master. It is a trailer-level source, not a brittle per-shot
    #: prompt, so the score remains coherent across clip regenerations.
    soundtrack_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    #: A real product photo placed locally during cinematic composition.
    product_reference_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )

    shots: Mapped[list["CinematicTrailerShot"]] = relationship(
        back_populates="trailer",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CinematicTrailerShot.position",
    )


class CinematicTrailerShot(TimestampMixin, Base):
    """One vendor task and its persisted AI clip inside a trailer."""

    __tablename__ = "cinematic_trailer_shots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trailer_id: Mapped[int] = mapped_column(
        ForeignKey("cinematic_trailers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    title_card: Mapped[str] = mapped_column(String(280), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    voiceover: Mapped[str] = mapped_column(Text, nullable=False)
    audio_cue: Mapped[str] = mapped_column(Text, nullable=False)
    reference_asset_urls: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    protect_reference: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Which verified Agentcy screen is composited into the finished shot.
    # This is separate from `mode`: protected screens never go to the model.
    product_surface: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    remote_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    provider_status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    provider_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    trailer: Mapped[CinematicTrailer] = relationship(back_populates="shots")


class Run(TimestampMixin, Base):
    """One completed pass of an agent or the crew, kept for the record.

    History outlives its campaign: `campaign_id` releases to NULL on delete and
    the campaign's name is denormalised here, because "what did the machine do
    last Tuesday" has to stay answerable after the campaign it did it for is
    gone.
    """

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True
    )
    campaign_name: Mapped[str] = mapped_column(String(255), nullable=False)

    #: "plan" (the planning agent), "generate" (the three-agent crew) or
    #: "render" (the studio).
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    #: "succeeded" or "failed".
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: One line, written for the history list — the same voice as the log.
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    #: The agent events exactly as the console received them, so opening a past
    #: run replays what was on screen rather than a summary of it.
    events: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    concepts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    variants: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    flagged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revisions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Which model produced this, recorded at run time — a plan written by the
    #: offline provider must never be mistaken later for one a model wrote.
    provider: Mapped[str] = mapped_column(String(40), default="", nullable=False)


class TrendSource(TimestampMixin, Base):
    """A keyword the trend scraper watches, and what it last found.

    The watchlist is the only steering a human has over what the planner treats
    as "the moment", so it is editable and it records its own last outcome —
    a source that silently stopped returning anything would otherwise look
    identical to one that is working.
    """

    __tablename__ = "trend_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword: Mapped[str] = mapped_column(String(200), nullable=False)
    geo: Mapped[str] = mapped_column(String(8), default="MY", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Why this keyword is watched — the human's reason, shown beside it.
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    #: "never", "live", "offline" or "failed" — how the last pull was answered.
    last_mode: Mapped[str] = mapped_column(String(20), default="never", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The signals themselves, so the watchlist can show what it is feeding the
    #: planner without a second round trip to Google.
    last_signals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
