"""Running the watchlist: keyword → signals → document → trend corpus.

One direction of travel, and it only ever ends in the trend corpus. Scraped
material is inspiration and can never become ground truth about the brand, so
this module has no path to the company knowledge base at all — the separation
the store draws between the two collections is enforced here by not having the
other function available rather than by remembering not to call it.

Each keyword becomes one markdown file on disk before it is ingested. The file
is the artefact a person can open and check, and re-scraping overwrites it in
place so the corpus never accumulates two generations of the same keyword.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.rag.ingest import TRENDS_DIR
from app.rag.store import KnowledgeStore
from app.trends import offline
from app.trends.serpapi_client import (
    DEFAULT_GEO,
    GoogleTrendsClient,
    TrendSignal,
    TrendsUnavailable,
)
from app.trends.serpapi_client import to_markdown as live_markdown

#: Where SerpApi responses are cached, beside the corpus they feed.
SNAPSHOT_DIR = TRENDS_DIR / "snapshots"


@dataclass
class ScrapeResult:
    """What one keyword produced this pass."""

    keyword: str
    geo: str
    #: "live" (SerpApi answered), "offline" (generated samples) or "failed".
    mode: str
    signals: list[TrendSignal]
    chunks: int = 0
    error: str | None = None
    document: str | None = None

    @property
    def ok(self) -> bool:
        return self.mode != "failed"


def slug(keyword: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-") or "keyword"


class TrendScraper:
    """Pulls a keyword's signals and files them in the trend corpus.

    `api_key` empty means no live source is configured, and the scraper says so
    by answering in offline mode rather than by failing. That is a deliberate
    choice for a product that has to be demonstrable: the alternative is a
    watchlist screen that does nothing at all until someone funds an account.
    """

    def __init__(
        self,
        *,
        store: KnowledgeStore,
        api_key: str = "",
        geo: str = DEFAULT_GEO,
        corpus_dir: Path | str = TRENDS_DIR,
        snapshot_dir: Path | str = SNAPSHOT_DIR,
    ) -> None:
        self.store = store
        self.api_key = api_key
        self.geo = geo
        self.corpus_dir = Path(corpus_dir)
        self.snapshot_dir = Path(snapshot_dir)

    @property
    def live(self) -> bool:
        return bool(self.api_key)

    def scrape(self, keyword: str, *, geo: str | None = None, refresh: bool = False) -> ScrapeResult:
        geo = geo or self.geo
        keyword = keyword.strip()
        if not keyword:
            return ScrapeResult(keyword, geo, "failed", [], error="the keyword is blank")

        if self.live:
            result = self._live(keyword, geo, refresh=refresh)
        else:
            signals = offline.sample(keyword, geo=geo)
            result = ScrapeResult(
                keyword, geo, "offline", signals, document=offline.to_markdown(keyword, signals)
            )

        if not result.ok or not result.signals:
            return result

        return self._file(result)

    def _live(self, keyword: str, geo: str, *, refresh: bool) -> ScrapeResult:
        try:
            client = GoogleTrendsClient(
                api_key=self.api_key, cache_dir=self.snapshot_dir, geo=geo
            )
            signals = client.related_queries(keyword, refresh=refresh)
        except (TrendsUnavailable, ValueError) as error:
            return ScrapeResult(keyword, geo, "failed", [], error=str(error))

        return ScrapeResult(
            keyword, geo, "live", signals, document=live_markdown(keyword, signals)
        )

    def _file(self, result: ScrapeResult) -> ScrapeResult:
        """Write the document, then ingest it — in that order, so what the
        corpus holds is always something that exists on disk to be checked."""
        path = self.corpus_dir / f"{result.geo.lower()}-{slug(result.keyword)}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result.document or "", encoding="utf-8")

        result.chunks = self.store.ingest_trends(
            result.document or "", source=path.name
        )
        return result
