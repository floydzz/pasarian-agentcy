import hashlib
import re

import pytest

from app.rag.store import (
    COMPANY_KB,
    TREND_CORPUS,
    KnowledgeStore,
    Retrieved,
    StaleCorpusError,
)

DIM = 64


def local_embedder(texts: list[str]) -> list[list[float]]:
    """Deterministic bag-of-words embedder — keeps these tests off the network
    while still exercising real Chroma similarity search."""
    vectors = []
    for text in texts:
        vector = [0.0] * DIM
        for token in re.findall(r"[a-z]+", text.lower()):
            bucket = int(hashlib.md5(token.encode()).hexdigest(), 16) % DIM
            vector[bucket] += 1.0
        norm = sum(v * v for v in vector) ** 0.5 or 1.0
        vectors.append([v / norm for v in vector])
    return vectors


@pytest.fixture
def store(tmp_path):
    return KnowledgeStore(path=tmp_path / "chroma", embedder=local_embedder)


BRAND_DOC = """# Brand voice

Warm bilingual Manglish. We never promise whitening or fairness.

## Hero product

The Embun hydrating serum targets humidity-clogged pores.
"""

TREND_DOC = """# TikTok Malaysia

The glass skin hashtag is surging among MY viewers this month.

## Shopee

Serum bundles trending ahead of the 9.9 sale.
"""


class TestCorporaStaySeparate:
    def test_trend_material_never_surfaces_in_a_company_query(self, store):
        store.ingest_company_kb(BRAND_DOC, source="brand.md")
        store.ingest_trends(TREND_DOC, source="tiktok.md")

        hits = store.retrieve_company("glass skin hashtag surging shopee", k=5)

        assert hits, "expected the company KB to return something"
        assert all(h.source == "brand.md" for h in hits)

    def test_company_material_never_surfaces_in_a_trend_query(self, store):
        store.ingest_company_kb(BRAND_DOC, source="brand.md")
        store.ingest_trends(TREND_DOC, source="tiktok.md")

        hits = store.retrieve_trends("brand voice whitening fairness", k=5)

        assert hits
        assert all(h.source == "tiktok.md" for h in hits)

    def test_the_two_collections_are_named_distinctly(self):
        assert COMPANY_KB != TREND_CORPUS


class TestRetrieval:
    def test_returns_the_most_similar_chunk_first(self, store):
        store.ingest_company_kb(BRAND_DOC, source="brand.md")
        top = store.retrieve_company("Embun hydrating serum humidity pores", k=2)[0]
        assert "Embun" in top.text

    def test_k_limits_the_number_of_hits(self, store):
        store.ingest_company_kb(BRAND_DOC, source="brand.md")
        assert len(store.retrieve_company("serum", k=1)) == 1

    def test_hits_carry_a_citable_chunk_id_and_heading(self, store):
        store.ingest_company_kb(BRAND_DOC, source="brand.md")
        hit = store.retrieve_company("hero product serum", k=1)[0]
        assert isinstance(hit, Retrieved)
        assert hit.chunk_id.startswith("brand.md#")
        assert hit.heading

    def test_querying_an_empty_corpus_returns_nothing(self, store):
        assert store.retrieve_trends("anything at all", k=3) == []


class TestIngestion:
    def test_reingesting_the_same_document_does_not_duplicate_chunks(self, store):
        store.ingest_company_kb(BRAND_DOC, source="brand.md")
        before = store.count(COMPANY_KB)
        store.ingest_company_kb(BRAND_DOC, source="brand.md")
        assert store.count(COMPANY_KB) == before

    def test_ingest_reports_how_many_chunks_landed(self, store):
        assert store.ingest_company_kb(BRAND_DOC, source="brand.md") == 2

    def test_persists_across_store_instances(self, tmp_path):
        path = tmp_path / "chroma"
        KnowledgeStore(path=path, embedder=local_embedder).ingest_company_kb(
            BRAND_DOC, source="brand.md"
        )
        reopened = KnowledgeStore(path=path, embedder=local_embedder)
        assert reopened.retrieve_company("serum", k=1)


def wider_embedder(texts: list[str]) -> list[list[float]]:
    """`local_embedder` at twice the width — a stand-in for switching
    EMBEDDING_PROVIDER, which is exactly what changes the vector width."""
    return [vector + vector for vector in local_embedder(texts)]


class TestASwitchedEmbeddingModel:
    """Vectors from two models are not comparable, and Chroma enforces that by
    width. A corpus embedded by the previous model is stale, not corrupt — the
    repair is to re-embed it, and the store's job is to say so.
    """

    def test_it_reports_the_width_of_what_is_stored(self, store):
        store.ingest_company_kb(BRAND_DOC, source="brand.md")
        assert store.dimension(COMPANY_KB) == DIM

    def test_an_empty_corpus_has_no_width_to_report(self, store):
        assert store.dimension(TREND_CORPUS) is None

    def test_querying_a_stale_corpus_says_what_to_do_about_it(self, tmp_path):
        path = tmp_path / "chroma"
        KnowledgeStore(path=path, embedder=local_embedder).ingest_company_kb(
            BRAND_DOC, source="brand.md"
        )
        switched = KnowledgeStore(path=path, embedder=wider_embedder)

        with pytest.raises(StaleCorpusError, match="ingest_kb.py"):
            switched.retrieve_company("serum", k=1)

    def test_the_message_names_the_corpus_and_both_widths(self, tmp_path):
        path = tmp_path / "chroma"
        KnowledgeStore(path=path, embedder=local_embedder).ingest_company_kb(
            BRAND_DOC, source="brand.md"
        )
        switched = KnowledgeStore(path=path, embedder=wider_embedder)

        with pytest.raises(StaleCorpusError) as raised:
            switched.retrieve_company("serum", k=1)

        assert COMPANY_KB in str(raised.value)
        assert str(DIM) in str(raised.value) and str(DIM * 2) in str(raised.value)

    def test_ensure_compatible_clears_only_the_stale_corpora(self, tmp_path):
        path = tmp_path / "chroma"
        seeded = KnowledgeStore(path=path, embedder=local_embedder)
        seeded.ingest_company_kb(BRAND_DOC, source="brand.md")

        switched = KnowledgeStore(path=path, embedder=wider_embedder)
        cleared = switched.ensure_compatible()

        assert cleared == [COMPANY_KB]
        assert switched.count(COMPANY_KB) == 0
        # And the store is usable again rather than merely diagnosed.
        switched.ingest_company_kb(BRAND_DOC, source="brand.md")
        assert switched.retrieve_company("serum", k=1)

    def test_a_matching_corpus_is_left_alone(self, store):
        store.ingest_company_kb(BRAND_DOC, source="brand.md")
        before = store.count(COMPANY_KB)

        assert store.ensure_compatible() == []
        assert store.count(COMPANY_KB) == before

    def test_it_costs_nothing_when_there_is_nothing_stored(self, tmp_path):
        calls = []

        def counting(texts: list[str]) -> list[list[float]]:
            calls.append(texts)
            return local_embedder(texts)

        store = KnowledgeStore(path=tmp_path / "chroma", embedder=counting)

        assert store.ensure_compatible() == []
        assert calls == []
