"""The console reads this route to know what the machine is made of."""

import pytest
from fastapi.testclient import TestClient

from app.api.system import read_system
from app.config import Settings
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _settings(**over):
    base = dict(
        database_url="mysql+pymysql://u:p@127.0.0.1:3307/agentcy",
        dashscope_api_key="ds-key",
    )
    base.update(over)
    return Settings(_env_file=None, **base)


def test_it_reports_the_active_providers(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.system.get_settings",
        lambda: _settings(llm_provider="qwen", embedding_provider="qwen"),
    )
    body = client.get("/api/system").json()
    assert body["llm_provider"] == "qwen"
    assert body["embedding_provider"] == "qwen"


class TestBrollAvailability:
    """The studio only offers the b-roll switch when it would do something."""

    def test_it_is_false_without_a_video_provider(self, monkeypatch):
        monkeypatch.setattr("app.api.system.get_settings", lambda: _settings())
        assert read_system().broll_available is False

    def test_it_is_true_for_a_keyed_dashscope_workspace(self, monkeypatch):
        monkeypatch.setattr(
            "app.api.system.get_settings",
            lambda: _settings(video_provider="dashscope"),
        )
        assert read_system().broll_available is True

    def test_a_provider_without_a_key_is_not_available(self, monkeypatch):
        monkeypatch.setattr(
            "app.api.system.get_settings",
            lambda: _settings(video_provider="dashscope", dashscope_api_key=""),
        )
        assert read_system().broll_available is False
