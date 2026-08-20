import pytest

from app.rag.ingest import (
    COMPANY_KB_DIR,
    TRENDS_DIR,
    ingest_all,
    ingest_directory,
)
from app.rag.store import COMPANY_KB, TREND_CORPUS, KnowledgeStore
from tests.test_store import local_embedder


@pytest.fixture
def store(tmp_path):
    return KnowledgeStore(path=tmp_path / "chroma", embedder=local_embedder)


@pytest.fixture
def docs(tmp_path):
    directory = tmp_path / "docs"
    directory.mkdir()
    (directory / "one.md").write_text("# One\n\nFirst document body.\n")
    (directory / "two.md").write_text("# Two\n\nSecond document body.\n")
    (directory / "notes.txt").write_text("not markdown, should be skipped")
    return directory


class TestIngestDirectory:
    def test_reports_chunks_landed_per_source_file(self, store, docs):
        assert ingest_directory(store, docs, corpus=COMPANY_KB) == {
            "one.md": 1,
            "two.md": 1,
        }

    def test_non_markdown_files_are_skipped(self, store, docs):
        ingest_directory(store, docs, corpus=COMPANY_KB)
        assert "notes.txt" not in ingest_directory(store, docs, corpus=COMPANY_KB)

    def test_the_filename_becomes_the_citable_source(self, store, docs):
        ingest_directory(store, docs, corpus=COMPANY_KB)
        hit = store.retrieve_company("first document body", k=1)[0]
        assert hit.source == "one.md"

    def test_a_missing_directory_names_the_path(self, store, tmp_path):
        with pytest.raises(FileNotFoundError, match="nowhere"):
            ingest_directory(store, tmp_path / "nowhere", corpus=COMPANY_KB)

    def test_an_unknown_corpus_is_rejected(self, store, docs):
        with pytest.raises(ValueError, match="corpus"):
            ingest_directory(store, docs, corpus="everything")

    def test_reingesting_a_directory_does_not_duplicate(self, store, docs):
        ingest_directory(store, docs, corpus=COMPANY_KB)
        before = store.count(COMPANY_KB)
        ingest_directory(store, docs, corpus=COMPANY_KB)
        assert store.count(COMPANY_KB) == before


class TestIngestAll:
    def test_loads_both_corpora_and_keeps_them_apart(self, store, tmp_path):
        company = tmp_path / "kb"
        company.mkdir()
        (company / "brand.md").write_text("# Voice\n\nWarm bilingual Manglish.\n")
        trends = tmp_path / "trends"
        trends.mkdir()
        (trends / "seed.md").write_text("# TikTok\n\nBarrier repair is climbing.\n")

        report = ingest_all(store, company_dir=company, trends_dir=trends)

        assert report.company == {"brand.md": 1}
        assert report.trends == {"seed.md": 1}
        assert store.count(COMPANY_KB) == 1
        assert store.count(TREND_CORPUS) == 1


class TestShippedCorpora:
    def test_the_bundled_company_kb_ingests(self, store):
        report = ingest_directory(store, COMPANY_KB_DIR, corpus=COMPANY_KB)
        assert set(report) == {"brand.md", "products.md", "campaigns.md"}
        assert all(count > 0 for count in report.values())

    def test_the_bundled_trend_seed_ingests(self, store):
        assert ingest_directory(store, TRENDS_DIR, corpus=TREND_CORPUS)

    def test_the_brand_guardrails_are_retrievable(self, store):
        ingest_directory(store, COMPANY_KB_DIR, corpus=COMPANY_KB)
        hits = store.retrieve_company("whitening fairness claims not allowed", k=3)
        assert any("whitening" in hit.text.lower() for hit in hits)
