"""Embed the bundled corpora into Chroma.

    python scripts/ingest_kb.py             # always re-embed
    python scripts/ingest_kb.py --if-empty  # only when the store is cold

Re-runnable: chunks are upserted by id, so editing a document and re-running
replaces its chunks rather than stacking duplicates beside them.

`--if-empty` exists for container start-up. Upserting is safe but not free —
with a real embedding provider every boot would re-embed the whole corpus and
be billed for it — so an already-populated store is left alone.

A corpus left by a *different* embedding model is the exception `--if-empty`
cannot see: it is fully populated and entirely unqueryable, because vectors of
two widths cannot be compared. That corpus is cleared and rebuilt on every run,
which is what turns changing EMBEDDING_PROVIDER into a restart.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.api.deps import get_store  # noqa: E402
from app.brand_profile import PROFILE_SOURCE, as_markdown  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import BrandProfile  # noqa: E402
from app.rag.ingest import TRENDS_DIR, ingest_all, ingest_directory  # noqa: E402
from app.rag.store import COMPANY_KB, TREND_CORPUS  # noqa: E402


def main(argv: list[str]) -> int:
    store = get_store()

    # Before anything else, and before `--if-empty` gets to decide: a corpus
    # embedded by a previous EMBEDDING_PROVIDER is not empty, but every query
    # against it fails on vector width. Clearing it here is what makes the
    # switch a restart rather than a manual volume wipe.
    for corpus in store.ensure_compatible():
        print(
            f"{corpus} was embedded by a different model — cleared, "
            "and re-embedded below"
        )

    with SessionLocal() as db:
        profile = db.scalar(select(BrandProfile).order_by(BrandProfile.id).limit(1))

    # A saved profile is authoritative even if a prior image left the bundled
    # demo corpus on the volume. This also restores the profile after Chroma is
    # cleared without requiring a person to open and re-save the form.
    if profile is not None:
        chunks = store.replace_company_kb(as_markdown(profile), source=PROFILE_SOURCE)
        print(
            f"\nbrand profile: {chunks} chunks embedded — "
            f"{store.count(COMPANY_KB)} in {COMPANY_KB}"
        )
        # The profile is authoritative over the company KB and says nothing
        # about trends, which live in their own corpus. A cold volume — or one
        # just cleared above — would otherwise leave the planner with no trend
        # signals at all, and it would never say so.
        if not store.count(TREND_CORPUS):
            counts = ingest_directory(store, TRENDS_DIR, corpus=TREND_CORPUS)
            print(
                f"trends: {sum(counts.values())} chunks embedded across "
                f"{len(counts)} documents"
            )
        return 0

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
