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


def test_scripted_demo_reports_the_forced_offline_runtime(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.system.get_settings",
        lambda: _settings(
            llm_provider="qwen",
            embedding_provider="qwen",
            video_provider="dashscope",
            scripted_demo=True,
        ),
    )

    body = client.get("/api/system").json()

    assert body["scripted_demo"] is True
    assert body["llm_provider"] == "demo"
    assert body["embedding_provider"] == "demo"
    assert body["broll_available"] is False


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


def test_readiness_is_registered_before_the_spa_fallback():
    from app.main import app
    readiness = next(index for index, route in enumerate(app.routes) if getattr(route, "path", None) == "/api/ready")
    fallbacks = [index for index, route in enumerate(app.routes) if getattr(route, "path", None) == ""]
    assert all(readiness < index for index in fallbacks)


def test_unknown_api_does_not_return_the_frontend(client):
    response = client.get('/api/this-endpoint-does-not-exist')
    assert response.status_code == 404
    assert response.json()['code'] == 'not_found'


def test_console_revalidates_documents_and_does_not_serve_html_for_missing_chunks(tmp_path):
    from fastapi import FastAPI
    from app.main import ConsoleFiles
    (tmp_path / 'index.html').write_text('<html>Current build</html>')
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'assets' / 'Dashboard-current.js').write_text('export const dashboard = true')
    console = FastAPI()
    console.mount('/', ConsoleFiles(directory=tmp_path, html=True))
    with TestClient(console) as client:
        for path in ('/', '/index.html', '/campaigns/23/image'):
            document = client.get(path)
            assert document.status_code == 200
            assert document.headers['cache-control'] == 'no-cache'
            assert 'Current build' in document.text
            cached = client.get(path, headers={'If-None-Match': document.headers['etag']})
            assert cached.status_code == 304
            assert cached.headers['cache-control'] == 'no-cache'
        chunk = client.get('/assets/Dashboard-current.js')
        assert chunk.status_code == 200
        assert 'immutable' in chunk.headers['cache-control']
        for path in ('/assets/Dashboard-old.js', '/assets/missing-font', '/missing.js'):
            missing = client.get(path)
            assert missing.status_code == 404
            assert 'text/html' not in missing.headers.get('content-type', '')
