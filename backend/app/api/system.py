"""What the machine is currently made of.

One route, read by the console's rail so the provider in use is on screen at
all times. That matters more than it sounds: `demo` produces copy that reads
like copy, and a rehearsal must never be mistaken on stage for a live model.
The answer is a fact about configuration, so nothing here touches the database
or the store.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(prefix="/api", tags=["ops"])


class SystemRead(BaseModel):
    llm_provider: str
    embedding_provider: str
    #: False when no SerpApi key is set — the watchlist then answers with
    #: generated samples, which is stated wherever those samples are shown.
    trends_live: bool
    geo: str
    #: False when no b-roll provider is configured or keyed. The video studio
    #: reads this to decide whether to offer the option at all, rather than
    #: showing a switch that quietly does nothing.
    broll_available: bool


@router.get("/system", response_model=SystemRead)
def read_system() -> SystemRead:
    settings = get_settings()
    return SystemRead(
        llm_provider=settings.llm_provider,
        embedding_provider=settings.embedding_provider,
        trends_live=bool(settings.serpapi_key),
        geo=settings.trends_geo,
        broll_available=settings.broll_is_available,
    )
