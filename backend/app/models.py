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

    #: "plan" (the planning agent) or "generate" (the three-agent crew).
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
