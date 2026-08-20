"""Loading the bundled corpora into the knowledge store.

Which directory a file lives in decides which corpus it lands in, and nothing
downstream can move it. That is the whole point: brand documents are ground
truth, trend documents are inspiration, and the boundary is drawn here at
ingestion time rather than left to a query filter that could be forgotten.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.rag.store import COMPANY_KB, TREND_CORPUS, KnowledgeStore

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
COMPANY_KB_DIR = DATA_DIR / "company_kb"
TRENDS_DIR = DATA_DIR / "trends"


@dataclass
class IngestReport:
    """Chunks written per source file, per corpus."""

    company: dict[str, int] = field(default_factory=dict)
    trends: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.company.values()) + sum(self.trends.values())


def ingest_directory(
    store: KnowledgeStore, directory: Path | str, *, corpus: str
) -> dict[str, int]:
    """Ingest every markdown file in `directory` into one corpus."""
    if corpus == COMPANY_KB:
        ingest = store.ingest_company_kb
    elif corpus == TREND_CORPUS:
        ingest = store.ingest_trends
    else:
        raise ValueError(
            f"unknown corpus {corpus!r} — expected {COMPANY_KB} or {TREND_CORPUS}"
        )

    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"no such corpus directory: {directory}")

    counts: dict[str, int] = {}
    for path in sorted(directory.glob("*.md")):
        counts[path.name] = ingest(path.read_text(), source=path.name)
    return counts


def ingest_all(
    store: KnowledgeStore,
    *,
    company_dir: Path | str = COMPANY_KB_DIR,
    trends_dir: Path | str = TRENDS_DIR,
) -> IngestReport:
    return IngestReport(
        company=ingest_directory(store, company_dir, corpus=COMPANY_KB),
        trends=ingest_directory(store, trends_dir, corpus=TREND_CORPUS),
    )
