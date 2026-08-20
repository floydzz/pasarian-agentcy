import hashlib
import re

import pytest

from app.rag.store import COMPANY_KB, TREND_CORPUS, KnowledgeStore, Retrieved

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
