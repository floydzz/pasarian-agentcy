import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.agents.cinematic_trailer import CinematicTrailerStudio
from app.api.deps import get_cinematic_trailer_studio
from app.db import get_db
from app.main import app
from app.media.storage import AssetStorage
from app.video.broll import VideoGenerationRequest, VideoGenerationTask
from app.video.trailer import RenderedTrailer

MP4 = b"\x00\x00\x00\x18ftypmp42fake"


class FakeProvider:
    def __init__(self):
        self.requests: list[VideoGenerationRequest] = []

    def submit_generation(self, request):
        self.requests.append(request)
        return VideoGenerationTask(f"task-{len(self.requests)}", "pending")

    def get_generation(self, task_id):
        return VideoGenerationTask(task_id, "succeeded", video_url=f"https://example.test/{task_id}.mp4")

    def download_generation(self, video_url):
        return MP4


class FakeComposer:
    def __init__(self):
        self.shots = []
        self.soundtrack = None
        self.reference_frames = []

    def render(self, shots, *, soundtrack=None):
        self.shots = shots
        self.soundtrack = soundtrack
        return RenderedTrailer(MP4, _png(), sum(shot.duration_seconds for shot in shots))

    def reference_frame(self, capture, *, offset_seconds):
        self.reference_frames.append((capture, offset_seconds))
        return b"exact-feature-frame"


def _png():
    image = Image.new("RGB", (1920, 1080), "midnightblue")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def storage(tmp_path):
    return AssetStorage(tmp_path)


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def composer():
    return FakeComposer()


@pytest.fixture
def studio(storage, provider, composer):
    return CinematicTrailerStudio(storage=storage, provider=provider, composer=composer)


@pytest.fixture
def client(session, studio):
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_cinematic_trailer_studio] = lambda: studio
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_default_preset_is_a_two_minute_product_story_with_ai_native_app_screens(client):
    response = client.post("/api/cinematic-trailers", json={})

    assert response.status_code == 201
    trailer = response.json()
    assert trailer["duration_seconds"] == 120
    assert trailer["shots"][-1]["title_card"] == "THIS VIDEO WAS MADE BY ME TOO"
    product_shots = [shot for shot in trailer["shots"] if shot["product_surface"] != "none"]
    assert {shot["product_surface"] for shot in product_shots} == {"studio", "hub", "history"}
    assert all(shot["mode"] == "reference_to_video" for shot in product_shots)
    assert not any(shot["protect_reference"] for shot in product_shots)
    assert all(shot["reference_asset_urls"][0].startswith("/media/") for shot in product_shots)


def _attach_capture(client, trailer_id):
    capture = "data:video/mp4;base64," + base64.b64encode(MP4).decode()
    response = client.post(
        f"/api/cinematic-trailers/{trailer_id}/application-capture",
        json={"data_url": capture},
    )
    assert response.status_code == 200


def test_feature_trailer_refuses_billed_generation_without_an_exact_ui_recording(client, provider):
    trailer = client.post("/api/cinematic-trailers", json={}).json()

    submitted = client.post(f"/api/cinematic-trailers/{trailer['id']}/submit")

    assert submitted.status_code == 409
    assert "guided Agentcy screen recording" in submitted.json()["detail"]
    assert provider.requests == []


def test_trailers_can_be_scoped_to_the_campaign_that_seeded_them(client, session):
    from app.models import Campaign

    campaign = Campaign(name="NailIt launch", brief="A luxury press-on launch.")
    session.add(campaign)
    session.commit()

    attached = client.post(
        "/api/cinematic-trailers", json={"campaign_id": campaign.id}
    )

    assert attached.status_code == 201
    assert attached.json()["campaign_id"] == campaign.id
    assert client.get(f"/api/cinematic-trailers?campaign_id={campaign.id}").json()[0]["id"] == attached.json()["id"]


def test_submitting_then_refreshing_persists_each_generated_shot(client, provider):
    trailer = client.post("/api/cinematic-trailers", json={}).json()
    _attach_capture(client, trailer["id"])

    submitted = client.post(f"/api/cinematic-trailers/{trailer['id']}/submit")
    assert submitted.status_code == 200
    assert len(provider.requests) == 4
    assert submitted.json()["status"] == "generating"

    refreshed = client.post(f"/api/cinematic-trailers/{trailer['id']}/refresh")
    assert refreshed.status_code == 200
    payload = refreshed.json()
    assert payload["status"] == "generating"
    assert len(provider.requests) == 8

    finished = client.post(f"/api/cinematic-trailers/{trailer['id']}/refresh")
    assert finished.status_code == 200
    payload = finished.json()
    assert payload["status"] == "generating"
    # The 120-second blueprint has more shots than one quota-sized batch.
    # Keep advancing until every durable task has been submitted rather than
    # silently tying the test to a particular trailer length.
    while len(provider.requests) < len(trailer["shots"]):
        client.post(f"/api/cinematic-trailers/{trailer['id']}/refresh")

    complete = client.post(f"/api/cinematic-trailers/{trailer['id']}/refresh")
    assert complete.status_code == 200
    assert complete.json()["status"] == "ready_to_compose"
    assert all(shot["media_url"].endswith(".mp4") for shot in complete.json()["shots"])


def test_composition_uses_the_exact_recording_for_ai_reference_without_pasting_it(client, provider, composer):
    trailer = client.post("/api/cinematic-trailers", json={}).json()
    _attach_capture(client, trailer["id"])
    client.post(f"/api/cinematic-trailers/{trailer['id']}/submit")
    # The first refresh completes the first rate-limited batch and queues the
    # first product-reference scene.
    client.post(f"/api/cinematic-trailers/{trailer['id']}/refresh")

    feature_index = next(
        index for index, shot in enumerate(trailer["shots"])
        if shot["label"] == "Marketing strategist"
    )
    feature_request = provider.requests[feature_index]
    assert feature_request.mode == "reference_to_video"
    assert feature_request.reference_images == (b"exact-feature-frame",)

    while len(provider.requests) < len(trailer["shots"]):
        client.post(f"/api/cinematic-trailers/{trailer['id']}/refresh")
    client.post(f"/api/cinematic-trailers/{trailer['id']}/refresh")
    composed = client.post(f"/api/cinematic-trailers/{trailer['id']}/compose")
    assert composed.status_code == 200
    assert composed.json()["status"] == "rendered"
    assert composed.json()["media_url"].endswith(".mp4")
    feature_shot = composer.shots[feature_index]
    assert feature_shot.application_image is None
    assert feature_shot.application_capture is None
    assert feature_shot.product_surface == "none"


def test_application_capture_supplies_exact_stills_without_becoming_a_screen_overlay(client, provider, composer):
    trailer = client.post("/api/cinematic-trailers", json={}).json()
    _attach_capture(client, trailer["id"])
    assert provider.requests == []

    client.post(f"/api/cinematic-trailers/{trailer['id']}/submit")
    while len(provider.requests) < len(trailer["shots"]):
        client.post(f"/api/cinematic-trailers/{trailer['id']}/refresh")
    client.post(f"/api/cinematic-trailers/{trailer['id']}/refresh")
    composed = client.post(f"/api/cinematic-trailers/{trailer['id']}/compose")

    assert composed.status_code == 200
    feature_shot = next(shot for shot in composer.shots if shot.title_card == "START WITH A CONVERSATION")
    assert feature_shot.application_capture is None
    assert feature_shot.application_image is None
    assert composer.reference_frames[0] == (MP4, 0.0)


def test_product_photo_is_composed_locally_and_never_sent_to_the_video_model(client, provider, composer):
    trailer = client.post("/api/cinematic-trailers", json={}).json()
    source = _png()
    product = "data:image/png;base64," + base64.b64encode(source).decode()
    attached = client.post(
        f"/api/cinematic-trailers/{trailer['id']}/product-reference",
        json={"data_url": product},
    )
    assert attached.status_code == 200
    assert attached.json()["product_reference_url"].endswith(".png")

    _attach_capture(client, trailer["id"])
    client.post(f"/api/cinematic-trailers/{trailer['id']}/submit")
    while len(provider.requests) < len(trailer["shots"]):
        client.post(f"/api/cinematic-trailers/{trailer['id']}/refresh")
    client.post(f"/api/cinematic-trailers/{trailer['id']}/refresh")
    composed = client.post(f"/api/cinematic-trailers/{trailer['id']}/compose")

    assert composed.status_code == 200
    assert all(source not in request.reference_images for request in provider.requests)
    assert all(shot.application_image is None for shot in composer.shots)
    assert all(shot.product_image == source for shot in composer.shots)
    assert all(shot.product_surface == "product" for shot in composer.shots)
    assert all(shot.application_capture is None for shot in composer.shots)

    # Replacing a local product source requires only a new free composition;
    # it never resubmits the already-paid AI source shots.
    replaced = client.post(
        f"/api/cinematic-trailers/{trailer['id']}/product-reference",
        json={"data_url": product},
    )
    assert replaced.status_code == 200
    assert replaced.json()["status"] == "ready_to_compose"
    assert replaced.json()["media_url"] is None
    assert len(provider.requests) == len(trailer["shots"])


def test_regeneration_keeps_the_saved_script_and_exact_ui_mapping(client, provider):
    trailer = client.post("/api/cinematic-trailers", json={}).json()
    _attach_capture(client, trailer["id"])
    client.post(f"/api/cinematic-trailers/{trailer['id']}/submit")
    while len(provider.requests) < len(trailer["shots"]):
        client.post(f"/api/cinematic-trailers/{trailer['id']}/refresh")
    completed = client.post(f"/api/cinematic-trailers/{trailer['id']}/refresh").json()
    original = next(shot for shot in completed["shots"] if shot["label"] == "Video Studio in motion")
    original_script = {
        field: original[field]
        for field in ("label", "title_card", "prompt", "duration_seconds", "voiceover", "audio_cue")
    }

    regenerated = client.post(
        f"/api/cinematic-trailers/{trailer['id']}/shots/{original['id']}/regenerate"
    )

    assert regenerated.status_code == 200
    new_take = next(shot for shot in regenerated.json()["shots"] if shot["id"] == original["id"])
    assert {field: new_take[field] for field in original_script} == original_script
    assert new_take["provider_status"] == "pending"
    assert new_take["media_url"] is None
    assert len(provider.requests) == len(trailer["shots"]) + 1


def test_soundtrack_upload_invalidates_only_the_finished_master(client, provider, composer):
    trailer = client.post("/api/cinematic-trailers", json={}).json()
    _attach_capture(client, trailer["id"])
    client.post(f"/api/cinematic-trailers/{trailer['id']}/submit")
    while len(provider.requests) < len(trailer["shots"]):
        client.post(f"/api/cinematic-trailers/{trailer['id']}/refresh")
    client.post(f"/api/cinematic-trailers/{trailer['id']}/refresh")
    rendered = client.post(f"/api/cinematic-trailers/{trailer['id']}/compose")
    assert rendered.status_code == 200
    source_count = len(provider.requests)
    audio = "data:audio/mpeg;base64," + base64.b64encode(b"ID3" + b"music" * 20).decode()

    attached = client.post(
        f"/api/cinematic-trailers/{trailer['id']}/soundtrack",
        json={"data_url": audio},
    )

    assert attached.status_code == 200
    assert attached.json()["soundtrack_url"].endswith(".mp3")
    assert attached.json()["status"] == "ready_to_compose"
    assert attached.json()["media_url"] is None
    assert len(provider.requests) == source_count


def test_reference_assets_are_validated_and_saved(client):
    raw = _png()
    data_url = "data:image/png;base64," + base64.b64encode(raw).decode()

    response = client.post("/api/cinematic-trailers/assets", json={"data_url": data_url})

    assert response.status_code == 201
    assert response.json()["media_url"].endswith(".png")
