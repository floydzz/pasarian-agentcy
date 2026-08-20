import json

import pytest

from app.trends.serpapi_client import (
    GoogleTrendsClient,
    TrendSignal,
    TrendsUnavailable,
    to_markdown,
)

RELATED_QUERIES = {
    "related_queries": {
        "rising": [
            {"query": "sunscreen no white cast", "extracted_value": 250},
            {"query": "skin barrier serum", "extracted_value": 90},
        ],
        "top": [{"query": "serum kulit berminyak", "extracted_value": 100}],
    }
}


class FakeFetch:
    """Stands in for the HTTP call — records params, replays canned payloads."""

    def __init__(self, *payloads):
        self.payloads = list(payloads) or [RELATED_QUERIES]
        self.calls: list[dict] = []

    def __call__(self, params: dict) -> dict:
        self.calls.append(dict(params))
        payload = self.payloads[min(len(self.calls) - 1, len(self.payloads) - 1)]
        if isinstance(payload, Exception):
            raise payload
        return payload


@pytest.fixture
def client(tmp_path):
    return GoogleTrendsClient(
        api_key="serp-key", fetch=FakeFetch(), cache_dir=tmp_path / "cache"
    )


class TestRequest:
    def test_queries_google_trends_for_malaysia(self, client):
        client.related_queries("serum")
        params = client.fetch.calls[0]
        assert params["engine"] == "google_trends"
        assert params["geo"] == "MY"
        assert params["q"] == "serum"
        assert params["api_key"] == "serp-key"

    def test_the_geo_is_configurable_for_other_markets(self, tmp_path):
        client = GoogleTrendsClient(
            api_key="k", fetch=FakeFetch(), cache_dir=tmp_path, geo="SG"
        )
        client.related_queries("serum")
        assert client.fetch.calls[0]["geo"] == "SG"

    def test_a_missing_api_key_names_the_env_var(self, tmp_path):
        with pytest.raises(ValueError, match="SERPAPI_KEY"):
            GoogleTrendsClient(api_key="", cache_dir=tmp_path)


class TestParsing:
    def test_rising_and_top_queries_are_distinguished(self, client):
        signals = client.related_queries("serum")
        rising = {s.query: s.rising for s in signals}
        assert rising["sunscreen no white cast"] is True
        assert rising["serum kulit berminyak"] is False

    def test_signals_are_ordered_by_strength(self, client):
        assert [s.value for s in client.related_queries("serum")] == [250, 100, 90]

    def test_limit_caps_the_number_of_signals(self, client):
        assert len(client.related_queries("serum", limit=2)) == 2

    def test_an_empty_payload_yields_no_signals(self, tmp_path):
        client = GoogleTrendsClient(
            api_key="k", fetch=FakeFetch({}), cache_dir=tmp_path
        )
        assert client.related_queries("serum") == []

    def test_a_serpapi_error_payload_is_raised(self, tmp_path):
        client = GoogleTrendsClient(
            api_key="k", fetch=FakeFetch({"error": "Invalid API key"}), cache_dir=tmp_path
        )
        with pytest.raises(TrendsUnavailable, match="Invalid API key"):
            client.related_queries("serum")


class TestSnapshotCache:
    def test_a_repeat_query_is_served_from_the_snapshot(self, client):
        client.related_queries("serum")
        client.related_queries("serum")
        assert len(client.fetch.calls) == 1

    def test_the_snapshot_survives_into_a_new_client(self, tmp_path):
        cache = tmp_path / "cache"
        GoogleTrendsClient(
            api_key="k", fetch=FakeFetch(), cache_dir=cache
        ).related_queries("serum")

        fresh = GoogleTrendsClient(api_key="k", fetch=FakeFetch(), cache_dir=cache)
        assert fresh.related_queries("serum")
        assert fresh.fetch.calls == []

    def test_a_live_failure_falls_back_to_the_snapshot(self, tmp_path):
        cache = tmp_path / "cache"
        GoogleTrendsClient(
            api_key="k", fetch=FakeFetch(), cache_dir=cache
        ).related_queries("serum")

        offline = GoogleTrendsClient(
            api_key="k",
            fetch=FakeFetch(ConnectionError("network down")),
            cache_dir=cache,
        )
        assert offline.related_queries("serum", refresh=True)

    def test_a_live_failure_without_a_snapshot_is_reported(self, tmp_path):
        client = GoogleTrendsClient(
            api_key="k",
            fetch=FakeFetch(ConnectionError("network down")),
            cache_dir=tmp_path / "cache",
        )
        with pytest.raises(TrendsUnavailable, match="network down"):
            client.related_queries("serum")

    def test_the_snapshot_is_readable_json_on_disk(self, client, tmp_path):
        client.related_queries("serum")
        snapshot = next((tmp_path / "cache").glob("*.json"))
        assert json.loads(snapshot.read_text())["related_queries"]


class TestMarkdownBridge:
    def test_signals_render_as_a_trend_corpus_document(self):
        signals = [
            TrendSignal(query="sunscreen no white cast", value=250, rising=True, geo="MY"),
            TrendSignal(query="serum kulit berminyak", value=100, rising=False, geo="MY"),
        ]

        document = to_markdown("serum", signals)

        assert document.startswith("# Google Trends")
        assert "sunscreen no white cast" in document
        assert "Rising" in document and "Top" in document

    def test_no_signals_still_renders_a_valid_document(self):
        assert to_markdown("serum", []).startswith("# Google Trends")
