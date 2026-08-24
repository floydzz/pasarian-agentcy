"""The trend watchlist: what the planner is allowed to call "the moment".

Steering happens here and nowhere else. The planner reads whatever is in the
trend corpus, so the watchlist below is the only lever a person has over that
input — which is why each keyword records its own last outcome, and why the
status route states plainly whether the signals behind it were measured or
generated. Scraped material is inspiration; it never reaches the company
knowledge base, and no route here can put it there.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_store
from app.api.schemas import (
    CorpusSourceRead,
    ScrapeRead,
    TrendSignalRead,
    TrendSourceCreate,
    TrendSourceRead,
    TrendSourceUpdate,
    TrendStatusRead,
)
from app.clock import utcnow
from app.config import get_settings
from app.db import get_db
from app.models import TrendSource
from app.rag.store import COMPANY_KB, TREND_CORPUS
from app.trends.scraper import ScrapeResult, TrendScraper

router = APIRouter(prefix="/api/trends", tags=["trends"])

#: Seeded on first read so the watchlist opens with something to run rather
#: than with an empty state and a form. These are the recurring pressures on a
#: Malaysian SME's calendar, not a guess at any one brand's category.
STARTERS = (
    ("raya promotion", "The retail peak the whole year is planned around."),
    ("merdeka sale", "August patriotism, heavy discounting, crowded feeds."),
    ("skincare malaysia", "Category demand — replace with your own category."),
    ("shopee live", "Where the buying actually happens, not just the browsing."),
)


def _scraper() -> TrendScraper:
    settings = get_settings()
    return TrendScraper(
        store=get_store(), api_key=settings.serpapi_key, geo=settings.trends_geo
    )


@router.get("/status", response_model=TrendStatusRead)
def status_() -> TrendStatusRead:
    settings = get_settings()
    store = get_store()
    return TrendStatusRead(
        live=bool(settings.serpapi_key),
        geo=settings.trends_geo,
        trend_chunks=store.count(TREND_CORPUS),
        company_chunks=store.count(COMPANY_KB),
        documents=[
            CorpusSourceRead(
                source=stored.source, chunks=stored.chunks, heading=stored.heading
            )
            for stored in store.sources(TREND_CORPUS)
        ],
    )


@router.get("/sources", response_model=list[TrendSourceRead])
def list_sources(db: Session = Depends(get_db)) -> list[TrendSource]:
    rows = list(db.scalars(select(TrendSource).order_by(TrendSource.id)))
    if rows:
        return rows

    geo = get_settings().trends_geo
    rows = [
        TrendSource(keyword=keyword, geo=geo, note=note) for keyword, note in STARTERS
    ]
    db.add_all(rows)
    db.commit()
    return rows


@router.post("/sources", response_model=TrendSourceRead, status_code=201)
def add_source(
    payload: TrendSourceCreate, db: Session = Depends(get_db)
) -> TrendSource:
    row = TrendSource(
        keyword=payload.keyword, geo=payload.geo.upper(), note=payload.note
    )
    db.add(row)
    db.commit()
    return row


@router.patch("/sources/{source_id}", response_model=TrendSourceRead)
def update_source(
    source_id: int, payload: TrendSourceUpdate, db: Session = Depends(get_db)
) -> TrendSource:
    row = _get(db, source_id)
    if payload.keyword is not None:
        keyword = payload.keyword.strip()
        if not keyword:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "the keyword must not be blank"
            )
        row.keyword = keyword
    if payload.note is not None:
        row.note = payload.note.strip() or None
    if payload.enabled is not None:
        row.enabled = payload.enabled
    db.commit()
    return row


@router.delete("/sources/{source_id}", status_code=204)
def remove_source(source_id: int, db: Session = Depends(get_db)) -> None:
    """Stops the keyword being scraped again.

    Chunks it already put in the corpus stay there — they are a real document
    on disk that the planner may already have cited, and silently retracting
    grounding under a concept a human approved is worse than a stale keyword.
    """
    db.delete(_get(db, source_id))
    db.commit()


@router.post("/scrape", response_model=list[ScrapeRead])
def scrape(
    source_id: int | None = None,
    refresh: bool = False,
    db: Session = Depends(get_db),
) -> list[ScrapeRead]:
    """Run the watchlist — or one keyword of it — and ingest what comes back."""
    query = select(TrendSource).order_by(TrendSource.id)
    if source_id is not None:
        query = query.where(TrendSource.id == source_id)
    else:
        query = query.where(TrendSource.enabled.is_(True))

    rows = list(db.scalars(query))
    if not rows:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "nothing to scrape — add a keyword or enable one",
        )

    scraper = _scraper()
    results: list[ScrapeRead] = []
    for row in rows:
        result = scraper.scrape(row.keyword, geo=row.geo, refresh=refresh)
        _record(row, result)
        results.append(
            ScrapeRead(
                source_id=row.id,
                keyword=row.keyword,
                mode=result.mode,
                chunks=result.chunks,
                signals=_signals(result),
                error=result.error,
            )
        )

    db.commit()
    return results


def _record(row: TrendSource, result: ScrapeResult) -> None:
    row.last_scraped_at = utcnow()
    row.last_mode = result.mode
    row.last_error = result.error
    if result.ok:
        # A failed pull leaves the previous signals in place: the watchlist
        # should show the last thing it actually knew, not go blank because
        # SerpApi was down for a minute.
        row.last_signals = [
            signal.model_dump() for signal in _signals(result)
        ]


def _signals(result: ScrapeResult) -> list[TrendSignalRead]:
    return [
        TrendSignalRead(query=signal.query, value=signal.value, rising=signal.rising)
        for signal in result.signals
    ]


def _get(db: Session, source_id: int) -> TrendSource:
    row = db.get(TrendSource, source_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trend source {source_id}")
    return row
