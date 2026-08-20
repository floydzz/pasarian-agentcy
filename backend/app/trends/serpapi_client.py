"""Google Trends (geo=MY) via SerpApi.

Every response is written to a snapshot on disk and every read prefers that
snapshot. Two reasons: SerpApi calls are metered, and a demo must not depend on
a live third-party call succeeding at the moment someone is watching. If the
network is down and a snapshot exists, the snapshot wins.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
DEFAULT_GEO = "MY"
DEFAULT_LIMIT = 10
#: SerpApi's own name for the Google Trends "related queries" view.
RELATED_QUERIES = "RELATED_QUERIES"

Fetch = Callable[[dict[str, Any]], dict[str, Any]]


class TrendsUnavailable(RuntimeError):
    """Trends could not be read live and no snapshot was available."""


@dataclass(frozen=True)
class TrendSignal:
    query: str
    #: Google's relative interest score; rising queries can exceed 100.
    value: int
    rising: bool
    geo: str

    @property
    def label(self) -> str:
        return "Rising" if self.rising else "Top"


def _http_fetch(params: dict[str, Any]) -> dict[str, Any]:
    response = httpx.get(SERPAPI_ENDPOINT, params=params, timeout=30.0)
    response.raise_for_status()
    return response.json()


class GoogleTrendsClient:
    def __init__(
        self,
        *,
        api_key: str,
        cache_dir: Path | str,
        fetch: Fetch | None = None,
        geo: str = DEFAULT_GEO,
    ) -> None:
        if not api_key:
            raise ValueError("missing SerpApi key — set SERPAPI_KEY")
        self.api_key = api_key
        self.geo = geo
        self.fetch = fetch or _http_fetch
        self.cache_dir = Path(cache_dir)

    def related_queries(
        self, keyword: str, *, limit: int = DEFAULT_LIMIT, refresh: bool = False
    ) -> list[TrendSignal]:
        """Queries rising and gaining alongside `keyword` in this market."""
        params = {
            "engine": "google_trends",
            "q": keyword,
            "geo": self.geo,
            "data_type": RELATED_QUERIES,
            "api_key": self.api_key,
        }
        payload = self._payload(keyword, params, refresh=refresh)
        return self._parse(payload)[:limit]

    # -- snapshots ---------------------------------------------------------

    def _payload(
        self, keyword: str, params: dict[str, Any], *, refresh: bool
    ) -> dict[str, Any]:
        snapshot = self._snapshot_path(keyword)

        if not refresh and snapshot.exists():
            return json.loads(snapshot.read_text())

        try:
            payload = self.fetch(params)
        except Exception as error:
            if snapshot.exists():
                # Demo-day resilience: a stale answer beats no answer.
                return json.loads(snapshot.read_text())
            raise TrendsUnavailable(f"could not reach SerpApi: {error}") from error

        if "error" in payload:
            raise TrendsUnavailable(str(payload["error"]))

        self._write_snapshot(snapshot, payload)
        return payload

    def _snapshot_path(self, keyword: str) -> Path:
        slug = re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-") or "query"
        digest = hashlib.sha1(f"{self.geo}:{keyword}".encode()).hexdigest()[:8]
        return self.cache_dir / f"{self.geo.lower()}-{slug}-{digest}.json"

    @staticmethod
    def _write_snapshot(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    # -- parsing -----------------------------------------------------------

    def _parse(self, payload: dict[str, Any]) -> list[TrendSignal]:
        related = payload.get("related_queries") or {}
        signals = [
            TrendSignal(
                query=entry.get("query", ""),
                value=int(entry.get("extracted_value") or entry.get("value") or 0),
                rising=(bucket == "rising"),
                geo=self.geo,
            )
            for bucket in ("rising", "top")
            for entry in related.get(bucket) or []
            if entry.get("query")
        ]
        return sorted(signals, key=lambda signal: signal.value, reverse=True)


def to_markdown(keyword: str, signals: list[TrendSignal]) -> str:
    """Render signals as a document the trend corpus can ingest.

    Headings mirror the chunker's expectations so each signal group becomes its
    own citable chunk.
    """
    geo = signals[0].geo if signals else DEFAULT_GEO
    lines = [
        f"# Google Trends — {keyword} ({geo})",
        "",
        "Search interest pulled from Google Trends. Search volume shows demand,",
        "not permission: a rising query still has to pass the brand guardrails.",
        "",
    ]

    for bucket, rising in (("Rising queries", True), ("Top queries", False)):
        matching = [signal for signal in signals if signal.rising is rising]
        if not matching:
            continue
        lines += [f"# {bucket} — {keyword}", ""]
        lines += [f"- {signal.query} ({signal.value})" for signal in matching]
        lines.append("")

    return "\n".join(lines)
