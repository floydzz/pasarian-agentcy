"""Embed the bundled corpora into Chroma.

    python scripts/ingest_kb.py             # always re-embed
    python scripts/ingest_kb.py --if-empty  # only when the store is cold

Re-runnable: chunks are upserted by id, so editing a document and re-running
replaces its chunks rather than stacking duplicates beside them.

`--if-empty` exists for container start-up. Upserting is safe but not free —
with a real embedding provider every boot would re-embed the whole corpus and
be billed for it — so an already-populated store is left alone.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.deps import get_store  # noqa: E402
from app.rag.ingest import ingest_all  # noqa: E402
from app.rag.store import COMPANY_KB, TREND_CORPUS  # noqa: E402


def main(argv: list[str]) -> int:
    store = get_store()

    if "--if-empty" in argv and store.count(COMPANY_KB):
        print(
            f"knowledge store already holds {store.count(COMPANY_KB)} company "
            f"chunks and {store.count(TREND_CORPUS)} trend chunks — skipping"
        )
        return 0

    report = ingest_all(store)

    for corpus, counts in (("company KB", report.company), ("trends", report.trends)):
        print(f"\n{corpus}:")
        for source, chunks in sorted(counts.items()):
            print(f"  {source:<20} {chunks:>3} chunks")

    print(
        f"\n{report.total} chunks embedded — "
        f"{store.count(COMPANY_KB)} in {COMPANY_KB}, "
        f"{store.count(TREND_CORPUS)} in {TREND_CORPUS}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
