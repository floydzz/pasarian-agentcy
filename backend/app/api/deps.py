"""Wiring the agents to the running app.

Both the knowledge store and the planning agent are FastAPI dependencies so a
test can swap in a stub without the app reaching for a network or an API key.
"""

from __future__ import annotations

from functools import lru_cache

from app.agents.planner import PlanningAgent
from app.config import Settings, get_settings
from app.llm import get_provider
from app.rag.embeddings import get_embedder
from app.rag.store import KnowledgeStore


@lru_cache
def _store(settings: Settings) -> KnowledgeStore:
    return KnowledgeStore(
        path=settings.chroma_dir,
        embedder=get_embedder(
            settings.embedding_provider,
            api_key=settings.active_embedding_key,
            model=settings.active_embedding_model,
        ),
    )


def get_store() -> KnowledgeStore:
    return _store(get_settings())


def get_planner() -> PlanningAgent:
    settings = get_settings()
    return PlanningAgent(
        provider=get_provider(
            settings.llm_provider,
            api_key=settings.active_llm_key,
            model=settings.active_llm_model,
        ),
        store=get_store(),
    )
