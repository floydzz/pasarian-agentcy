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
