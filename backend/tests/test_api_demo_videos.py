import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.agents.demo_video import DemoVideoSpec, RenderedDemoVideo
from app.api.deps import get_demo_video_studio
from app.db import get_db
from app.main import app
from app.media.storage import AssetStorage


class StubDemoVideoStudio:
    def __init__(self, storage):
        self.storage = storage
        self.calls = 0

    def run(self, spec: DemoVideoSpec) -> RenderedDemoVideo:
        self.calls += 1
        self.last = spec
        poster = Image.new("RGB", (720, 1280), "navy")
        output = io.BytesIO()
        poster.save(output, format="PNG")
        return RenderedDemoVideo(
            media_url=self.storage.save(b"\x00\x00\x00\x18ftypmp42", suffix=".mp4"),
            poster_url=self.storage.save(output.getvalue(), suffix=".png"),
            duration_seconds=18,
            scene_count=6,
            qa_status="passed",
            qa_notes=None,
        )


@pytest.fixture
def storage(tmp_path):
    return AssetStorage(tmp_path)


@pytest.fixture
def studio(storage):
    return StubDemoVideoStudio(storage)


@pytest.fixture
def client(session, studio):
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_demo_video_studio] = lambda: studio
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_empty_workspace_has_no_product_explainer_yet(client):
    response = client.get("/api/demo-videos")

    assert response.status_code == 200
    assert response.json() == []


def test_rendering_creates_a_reviewable_vertical_mp4(client, storage):
    response = client.post("/api/demo-videos/render", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["title"].startswith("Marketing should move")
    assert body["media_url"].endswith(".mp4")
    assert body["poster_url"].endswith(".png")
    assert body["duration_seconds"] == 18
    assert body["scene_count"] == 6
    assert body["qa_status"] == "passed"
    assert body["review_status"] == "pending"
    assert storage.read(body["media_url"]).startswith(b"\x00\x00\x00\x18ftyp")


def test_rendering_rejects_blank_message_fields(client):
    response = client.post("/api/demo-videos/render", json={"title": "   "})

    assert response.status_code == 422


def test_a_human_can_approve_or_reject_the_video(client):
    video_id = client.post("/api/demo-videos/render", json={}).json()["id"]

    assert client.post(f"/api/demo-videos/{video_id}/approve").json()["review_status"] == "approved"
    assert client.post(f"/api/demo-videos/{video_id}/reject").json()["review_status"] == "rejected"


def test_a_redo_replaces_both_export_and_review_files(client, storage):
    original = client.post("/api/demo-videos/render", json={}).json()
    replacement = client.post(f"/api/demo-videos/{original['id']}/redo").json()

    assert replacement["media_url"] != original["media_url"]
    assert replacement["poster_url"] != original["poster_url"]
    assert replacement["review_status"] == "pending"
    assert not storage.path_for(original["media_url"]).exists()
    assert not storage.path_for(original["poster_url"]).exists()


class TestAskingForGeneratedBackdrops:
    """The b-roll switch has to survive the trip from the form to the studio.

    It is worth a test of its own because getting it wrong is silent and
    expensive in both directions: dropped, and the film renders painted while
    the console says otherwise; defaulted on, and every render spends six paid
    clips nobody asked for.
    """

    def test_the_flag_reaches_the_studio(self, client, studio):
        client.post("/api/demo-videos/render", json={"use_broll": True})

        assert studio.last.use_broll is True

    def test_it_is_off_unless_it_is_asked_for(self, client, studio):
        client.post("/api/demo-videos/render", json={})

        assert studio.last.use_broll is False
