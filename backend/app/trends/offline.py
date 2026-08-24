"""Trend signals without a SerpApi key. Samples, not measurements.

The risk register says the demo must not depend on a live third-party call, and
a trend watchlist that only works with a funded key is a watchlist that cannot
be rehearsed. This produces the *shape* of a Google Trends answer — Malaysian
search modifiers around the watched keyword, scored and split into rising and
top — so the scrape, the ingest, the chunking and the planner's citation
checking all run for real against it.

What it is not is data. Nothing here was measured. Every document it writes
says so in its heading, so a concept grounded in one of these chunks carries
that admission into the citation a reviewer reads.
"""

from __future__ import annotations

import hashlib

from app.trends.serpapi_client import DEFAULT_GEO, TrendSignal

#: How Malaysians actually qualify a product search — price first, marketplace
#: second, proof third. Ordered so the generated set reads like a real tail.
MODIFIERS = (
    ("harga {keyword}", True),
    ("{keyword} murah", True),
    ("{keyword} shopee", True),
    ("{keyword} viral tiktok", True),
    ("{keyword} review jujur", True),
    ("{keyword} terbaik malaysia", False),
    ("{keyword} online", False),
    ("beli {keyword} lazada", False),
    ("{keyword} berdekatan", False),
    ("promosi {keyword}", False),
)


def sample(keyword: str, *, geo: str = DEFAULT_GEO, limit: int = 10) -> list[TrendSignal]:
    """A stable set of sample signals for `keyword`.

    Seeded from the keyword itself, so the same watchlist produces the same
    signals every time it is scraped. A rehearsal that reshuffles its own data
    between runs is a rehearsal you cannot trust.
    """
    keyword = keyword.strip()
    if not keyword:
        return []

    lowered = keyword.lower()
    seed = int(hashlib.sha1(f"{geo}:{lowered}".encode()).hexdigest()[:8], 16)

    # A modifier the keyword already contains produces "shopee live shopee",
    # which no one has ever typed into a search box.
    words = set(lowered.split())
    usable = [
        (template, rising)
        for template, rising in MODIFIERS
        if not words & set(template.format(keyword="").split())
    ]

    signals = [
        TrendSignal(
            query=template.format(keyword=lowered),
            # Rising queries are scored as breakout-style multiples the way
            # Google reports them; top queries stay on the 0–100 scale.
            value=(250 + (seed >> (index * 3)) % 700) if rising
            else (100 - (seed >> (index * 2)) % 55),
            rising=rising,
            geo=geo,
        )
        for index, (template, rising) in enumerate(usable)
    ]
    return sorted(signals, key=lambda signal: signal.value, reverse=True)[:limit]


def to_markdown(keyword: str, signals: list[TrendSignal]) -> str:
    """Render samples for the trend corpus, labelled as samples in the heading.

    The heading is what a citation shows, so the label travels with the chunk
    all the way to the reviewer rather than living only in this file.
    """
    geo = signals[0].geo if signals else DEFAULT_GEO
    lines = [
        f"# Offline trend sample — {keyword} ({geo})",
        "",
        "These are generated samples, not measured search interest. They are "
        "here so the pipeline can be rehearsed without a SerpApi key. Treat "
        "anything grounded in this document as unverified.",
        "",
    ]

    for bucket, rising in (("Rising queries", True), ("Top queries", False)):
        matching = [signal for signal in signals if signal.rising is rising]
        if not matching:
            continue
        lines += [f"# {bucket} (sample) — {keyword}", ""]
        lines += [f"- {signal.query} ({signal.value})" for signal in matching]
        lines.append("")

    return "\n".join(lines)
