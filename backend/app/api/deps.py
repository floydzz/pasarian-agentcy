"""Wiring the agents to the running app.

Both the knowledge store and the planning agent are FastAPI dependencies so a
test can swap in a stub without the app reaching for a network or an API key.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import tuning
from app.agents.copywriter import Copywriter
from app.agents.crew import GenerationCrew
from app.agents.director import Director
from app.agents.planner import PlanningAgent
from app.agents.studio import Studio
from app.agents.vision_qa import VisionQA
from app.agents.visual_planner import VisualPlanner
from app.config import get_settings
from app.db import get_db
from app.llm import get_provider
from app.media import get_media_provider
from app.media.storage import AssetStorage
from app.models import AgentSetting, Campaign
from app.rag.embeddings import get_embedder
from app.rag.store import KnowledgeStore


def get_campaign_or_404(db: Session, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no campaign {campaign_id}")
    return campaign


@lru_cache
def get_store() -> KnowledgeStore:
    """One store per process — opening Chroma per request is wasteful.

    Cached on no arguments rather than on `Settings`: a pydantic settings object
    is not hashable, and `get_settings()` is itself cached, so there is only
    ever one configuration to key on anyway.
    """
    settings = get_settings()
    return KnowledgeStore(
        path=settings.chroma_dir,
        embedder=get_embedder(
            settings.embedding_provider,
            api_key=settings.active_embedding_key,
            model=settings.active_embedding_model,
        ),
    )


def _llm(*, vision: bool = False):
    """The provider the agents talk to.

    `vision=True` is for the QA pass, which sends an image. It resolves to the
    same model unless a vision model is pinned separately — see
    `Settings.active_vision_model`.
    """
    settings = get_settings()
    return get_provider(
        settings.llm_provider,
        api_key=settings.active_llm_key,
        model=settings.active_vision_model if vision else settings.active_llm_model,
        reasoning=settings.llm_reasoning,
        fallback_models=settings.llm_fallback_chain,
    )


class Tuning:
    """Every agent's saved settings, read once and merged over the defaults.

    Read per request rather than cached: changing a knob on the agents screen
    has to affect the very next run, or the screen is lying about what the
    machine is doing.
    """

    def __init__(self, db: Session) -> None:
        self._rows = {
            row.agent: row for row in db.scalars(select(AgentSetting))
        }

    def value(self, agent: str, field: str) -> int:
        saved = getattr(self._rows.get(agent), field, None)
        if saved is None:
            return tuning.defaults(agent)[field]
        return tuning.clamp(agent, field, saved)

    def note(self, agent: str) -> str | None:
        return getattr(self._rows.get(agent), "standing_note", None)


def get_tuning(db: Session = Depends(get_db)) -> Tuning:
    return Tuning(db)


def get_planner(tuned: Tuning = Depends(get_tuning)) -> PlanningAgent:
    return PlanningAgent(
        provider=_llm(),
        store=get_store(),
        standing_note=tuned.note(tuning.PLANNER),
        concept_count=tuned.value(tuning.PLANNER, "concept_count"),
        company_k=tuned.value(tuning.PLANNER, "company_k"),
        trend_k=tuned.value(tuning.PLANNER, "trend_k"),
    )


def get_crew(tuned: Tuning = Depends(get_tuning)) -> GenerationCrew:
    # All three agents share one provider: swapping the model in .env swaps the
    # whole crew, so the copy and the review it faces never come from different
    # models by accident. They share one retrieval width for the same reason.
    provider = _llm()
    return GenerationCrew(
        copywriter=Copywriter(
            provider=provider, standing_note=tuned.note(tuning.COPYWRITER)
        ),
        visual_planner=VisualPlanner(
            provider=provider, standing_note=tuned.note(tuning.VISUAL_PLANNER)
        ),
        director=Director(
            provider=provider, standing_note=tuned.note(tuning.DIRECTOR)
        ),
        store=get_store(),
        max_revisions=tuned.value(tuning.DIRECTOR, "max_revisions"),
        company_k=tuned.value(tuning.COPYWRITER, "company_k"),
    )


@lru_cache
def get_storage() -> AssetStorage:
    """One storage per process, for the same reason `get_store` is cached."""
    return AssetStorage(get_settings().assets_dir)


def get_studio(tuned: Tuning = Depends(get_tuning)) -> Studio:
    settings = get_settings()
    return Studio(
        provider=get_media_provider(
            settings.media_provider,
            api_key=settings.active_media_key,
            image_model=settings.active_media_model,
            timeout_seconds=settings.media_timeout_seconds,
        ),
        # QA judges with the same model the crew wrote with, for the same
        # reason the crew shares one provider: a reviewer and the thing it
        # reviews should not come from different models by accident.
        qa=VisionQA(provider=_llm(vision=True), standing_note=tuned.note(tuning.VISION_QA)),
        storage=get_storage(),
        max_redos=tuned.value(tuning.VISION_QA, "max_redos"),
    )
