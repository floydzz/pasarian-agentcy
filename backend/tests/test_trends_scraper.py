import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models import TrendSource
from app.rag.store import COMPANY_KB, TREND_CORPUS
from app.trends import offline
from app.trends.scraper import TrendScraper, slug


class FakeStore:
    """Records what was ingested, and into which corpus.

    Deliberately offers no company-knowledge method: the point of the test is
    that the scraper cannot write scraped material into ground truth, and the
    cheapest proof is that the call would not exist.
    """

    def __init__(self) -> None:
        self.trend_writes: list[tuple[str, str]] = []

    def ingest_trends(self, markdown: str, *, source: str) -> int:
        self.trend_writes.append((source, markdown))
        return markdown.count("\n- ")


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
def scraper(store, tmp_path):
    return TrendScraper(store=store, api_key="", corpus_dir=tmp_path)


@pytest.fixture
def client(session):
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestOfflineSamples:
    def test_the_same_keyword_always_produces_the_same_signals(self):
        """A rehearsal that reshuffles its own data is one you cannot trust."""
        first = offline.sample("raya promotion")
        second = offline.sample("raya promotion")
        assert [signal.query for signal in first] == [
            signal.query for signal in second
        ]

    def test_different_keywords_produce_different_scores(self):
        raya = {signal.value for signal in offline.sample("raya promotion")}
        merdeka = {signal.value for signal in offline.sample("merdeka sale")}
        assert raya != merdeka

    def test_both_rising_and_top_queries_are_produced(self):
        signals = offline.sample("skincare")
        assert any(signal.rising for signal in signals)
        assert any(not signal.rising for signal in signals)

    def test_a_modifier_the_keyword_already_contains_is_dropped(self):
        """Nobody has ever searched for "shopee live shopee"."""
        queries = [signal.query for signal in offline.sample("shopee live")]
        assert not any(query.count("shopee") > 1 for query in queries)

    def test_a_blank_keyword_produces_nothing(self):
        assert offline.sample("   ") == []

    def test_the_document_admits_it_was_not_measured(self):
        """The admission has to travel with the chunk to the reviewer."""
        markdown = offline.to_markdown("raya", offline.sample("raya"))
        assert markdown.startswith("# Offline trend sample — raya")
        assert "not measured search interest" in markdown


class TestTheScraper:
    def test_without_a_key_it_answers_offline_rather_than_failing(self, scraper):
        """A watchlist that does nothing without a funded account is not a demo."""
        result = scraper.scrape("raya promotion")
        assert result.mode == "offline"
        assert result.ok
        assert result.signals

    def test_what_it_pulls_lands_in_the_trend_corpus(self, scraper, store):
        scraper.scrape("raya promotion")
        assert len(store.trend_writes) == 1
        source, markdown = store.trend_writes[0]
        assert source == "my-raya-promotion.md"
        assert "raya promotion" in markdown

    def test_the_document_is_on_disk_before_it_is_ingested(self, scraper, tmp_path):
        """The file is the artefact a person can open and check."""
        scraper.scrape("raya promotion")
        written = tmp_path / "my-raya-promotion.md"
        assert written.exists()
        assert "Offline trend sample" in written.read_text()

    def test_rescraping_overwrites_rather_than_stacking_a_second_generation(
        self, scraper, tmp_path
    ):
        scraper.scrape("raya promotion")
        scraper.scrape("raya promotion")
        assert len(list(tmp_path.glob("*.md"))) == 1

    def test_a_blank_keyword_fails_without_writing_anything(self, scraper, store):
        result = scraper.scrape("   ")
        assert result.mode == "failed"
        assert store.trend_writes == []

    def test_the_scraper_has_no_route_into_company_knowledge(self, scraper):
        """Scraped material is inspiration; it can never become ground truth."""
        assert not hasattr(scraper.store, "ingest_company_kb")

    def test_slugs_are_stable_and_filesystem_safe(self):
        assert slug("Hari Raya — hamper!") == "hari-raya-hamper"
        assert slug("!!!") == "keyword"


class TestTheWatchlistApi:
    def test_the_watchlist_seeds_itself_so_there_is_something_to_run(self, client):
        payload = client.get("/api/trends/sources").json()
        assert len(payload) >= 1
        assert all(source["last_mode"] == "never" for source in payload)

    def test_seeding_happens_once(self, client):
        first = client.get("/api/trends/sources").json()
        second = client.get("/api/trends/sources").json()
        assert [s["id"] for s in first] == [s["id"] for s in second]

    def test_a_keyword_can_be_added(self, client):
        client.get("/api/trends/sources")
        response = client.post(
            "/api/trends/sources",
            json={"keyword": "hari raya hamper", "note": "Gifting peaks early."},
        )
        assert response.status_code == 201
        assert response.json()["keyword"] == "hari raya hamper"
        assert response.json()["enabled"] is True

    def test_a_keyword_can_be_disabled_without_being_deleted(self, client):
        source = client.get("/api/trends/sources").json()[0]
        response = client.patch(
            f"/api/trends/sources/{source['id']}", json={"enabled": False}
        )
        assert response.json()["enabled"] is False

    def test_a_blank_keyword_is_refused(self, client):
        source = client.get("/api/trends/sources").json()[0]
        response = client.patch(
            f"/api/trends/sources/{source['id']}", json={"keyword": "   "}
        )
        assert response.status_code == 422

    def test_removing_a_keyword_stops_it_being_scraped_again(self, client, session):
        source = client.get("/api/trends/sources").json()[0]
        assert client.delete(f"/api/trends/sources/{source['id']}").status_code == 204
        assert session.get(TrendSource, source["id"]) is None

    def test_an_unknown_source_is_a_404(self, client):
        assert client.patch("/api/trends/sources/9999", json={}).status_code == 404

    def test_scraping_records_what_each_keyword_last_returned(self, client):
        client.get("/api/trends/sources")
        results = client.post("/api/trends/scrape").json()
        assert results
        assert all(result["mode"] == "offline" for result in results)

        after = client.get("/api/trends/sources").json()
        assert all(source["last_mode"] == "offline" for source in after)
        assert all(source["last_signals"] for source in after)

    def test_a_disabled_keyword_is_skipped_by_a_full_pull(self, client):
        sources = client.get("/api/trends/sources").json()
        client.patch(f"/api/trends/sources/{sources[0]['id']}", json={"enabled": False})
        results = client.post("/api/trends/scrape").json()
        assert sources[0]["id"] not in {result["source_id"] for result in results}

    def test_one_keyword_can_be_pulled_on_its_own(self, client):
        sources = client.get("/api/trends/sources").json()
        results = client.post(
            f"/api/trends/scrape?source_id={sources[0]['id']}"
        ).json()
        assert len(results) == 1
        assert results[0]["source_id"] == sources[0]["id"]

    def test_a_disabled_keyword_can_still_be_pulled_deliberately(self, client):
        """Naming it is an explicit act; the toggle only governs the bulk run."""
        sources = client.get("/api/trends/sources").json()
        client.patch(f"/api/trends/sources/{sources[0]['id']}", json={"enabled": False})
        results = client.post(
            f"/api/trends/scrape?source_id={sources[0]['id']}"
        ).json()
        assert len(results) == 1

    def test_scraping_an_empty_watchlist_says_so(self, client, session):
        for source in client.get("/api/trends/sources").json():
            client.delete(f"/api/trends/sources/{source['id']}")
        assert client.post("/api/trends/scrape").status_code == 409


class TestTheStatusRoute:
    def test_it_states_plainly_whether_the_signals_were_measured(self, client):
        payload = client.get("/api/trends/status").json()
        assert payload["live"] is False

    def test_it_reports_both_corpora_separately(self, client):
        """Their separation is the load-bearing idea, so it is never one number."""
        payload = client.get("/api/trends/status").json()
        assert "trend_chunks" in payload
        assert "company_chunks" in payload


class TestTheCorporaStaySeparate:
    def test_the_two_collections_are_not_the_same_collection(self):
        assert COMPANY_KB != TREND_CORPUS
