import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.agents.events import AgentEvent
from app.agents.video_studio import MarketingVideoSpec, RenderedMarketingVideo
from app.api.deps import get_storage, get_video_studio
from app.db import get_db
from app.main import app
from app.media.storage import AssetStorage


class StubVideoStudio:
    def __init__(self, storage):
        self.storage = storage
        self.seen: list[MarketingVideoSpec] = []

    def run(self, spec: MarketingVideoSpec, *, sink=None) -> RenderedMarketingVideo:
        self.seen.append(spec)
        if sink is not None:
            for agent, detail in (
                ("planner", "Reading the video brief"),
                ("visual_planner", "Mapping the storyboard"),
                ("renderer", "Encoding the MP4"),
                ("vision_qa", "Checking the review frame"),
            ):
                sink(AgentEvent(agent, "started", detail))
                sink(AgentEvent(agent, "finished", f"{detail} complete"))
        poster = Image.new("RGB", (720, 1280), "darkgreen")
        output = io.BytesIO()
        poster.save(output, format="PNG")
        return RenderedMarketingVideo(
            media_url=self.storage.save(b"\x00\x00\x00\x18ftypmp42", suffix=".mp4"),
            poster_url=self.storage.save(output.getvalue(), suffix=".png"),
            duration_seconds=len(spec.storyboard) * 3,
            scene_count=len(spec.storyboard),
            qa_status="passed",
            qa_notes=None,
        )


@pytest.fixture
def storage(tmp_path):
    return AssetStorage(tmp_path)


@pytest.fixture
def studio(storage):
    return StubVideoStudio(storage)


@pytest.fixture
def client(session, studio):
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_video_studio] = lambda: studio
    app.dependency_overrides[get_storage] = lambda: studio.storage
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def custom_payload():
    return {
        "name": "Rumah Blend launch",
        "profile": "product_marketing",
        "brand_name": "Kawan Kopi",
        "product_name": "Rumah Blend",
        "target_audience": "Kuala Lumpur home coffee brewers",
        "cta": "Try Rumah Blend",
        "storyboard": [
            {"eyebrow": "Meet the blend", "headline": "Coffee that starts at home", "body": "Freshly roasted for the daily cup.", "layout": "hero"},
            {"eyebrow": "What makes it different", "headline": "Built for how you brew", "body": "Chocolatey, balanced and approachable.", "layout": "feature"},
            {"eyebrow": "Your next cup", "headline": "Bring better coffee home", "body": "Start with the blend made for your routine.", "layout": "cta"},
        ],
    }


def test_studio_opens_on_an_agentcy_software_demo_preset(client):
    response = client.post("/api/videos/render", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["profile"] == "software_demo"
    assert body["brand_name"] == "Agentcy"
    assert body["scene_count"] == 5
    assert len(body["storyboard"]) == 5


def test_studio_renders_a_different_marketing_video_from_its_own_storyboard(client, studio):
    response = client.post("/api/videos/render", json=custom_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["brand_name"] == "Kawan Kopi"
    assert body["product_name"] == "Rumah Blend"
    assert body["duration_seconds"] == 9
    assert body["scene_count"] == 3
    assert studio.seen[0].storyboard[1].layout == "feature"


def test_a_video_needs_at_least_three_scenes(client):
    payload = custom_payload()
    payload["storyboard"] = payload["storyboard"][:2]

    assert client.post("/api/videos/render", json=payload).status_code == 422


def test_redo_uses_the_saved_generic_storyboard_and_replaces_files(client, storage, studio):
    original = client.post("/api/videos/render", json=custom_payload()).json()
    replacement = client.post(f"/api/videos/{original['id']}/redo").json()

    assert replacement["media_url"] != original["media_url"]
    assert replacement["review_status"] == "pending"
    assert studio.seen[-1].brand_name == "Kawan Kopi"
    assert len(studio.seen[-1].storyboard) == 3
    assert not storage.path_for(original["media_url"]).exists()
    assert not storage.path_for(original["poster_url"]).exists()


def test_generic_video_has_its_own_review_gate(client):
    video_id = client.post("/api/videos/render", json=custom_payload()).json()["id"]

    assert client.post(f"/api/videos/{video_id}/approve").json()["review_status"] == "approved"
    assert client.post(f"/api/videos/{video_id}/reject").json()["review_status"] == "rejected"


def test_streaming_video_render_narrates_each_agent_then_returns_the_video(client):
    body = client.post("/api/videos/render/stream", json=custom_payload()).text
    lines = [line for line in body.splitlines() if line]

    assert '"agent": "planner"' in lines[0]
    assert any('"agent": "renderer"' in line for line in lines)
    assert any('"agent": "vision_qa"' in line for line in lines)
    assert '"kind": "result"' in lines[-1]
    assert '"name": "Rumah Blend launch"' in lines[-1]


# -- campaign scoping ------------------------------------------------------


def a_campaign(client, name="Raya launch", brief="Sell the festive gift set."):
    return client.post("/api/campaigns", json={"name": name, "brief": brief}).json()


def test_a_video_made_in_a_campaign_belongs_to_it(client):
    campaign = a_campaign(client)

    body = client.post(
        f"/api/campaigns/{campaign['id']}/videos/render", json=custom_payload()
    ).json()

    assert body["campaign_id"] == campaign["id"]
    assert client.get(f"/api/campaigns/{campaign['id']}/videos").json()[0]["id"] == body["id"]


def test_campaign_video_locks_the_selected_product_photo(client, studio):
    campaign = a_campaign(client)
    product = Image.new("RGB", (400, 400), "darkorange")
    output = io.BytesIO()
    product.save(output, format="PNG")
    source = output.getvalue()
    reference = client.post(
        f"/api/campaigns/{campaign['id']}/product-references",
        json={
            "label": "Coffee bag",
            "data_url": "data:image/png;base64," + base64.b64encode(source).decode(),
        },
    ).json()

    rendered = client.post(
        f"/api/campaigns/{campaign['id']}/videos/render",
        json={**custom_payload(), "product_reference_id": reference["id"]},
    )

    assert rendered.status_code == 200
    assert rendered.json()["product_reference_url"] == reference["media_url"]
    assert studio.seen[-1].product_image == source


def test_a_video_made_outside_a_campaign_belongs_to_none(client):
    assert client.post("/api/videos/render", json=custom_payload()).json()["campaign_id"] is None


def test_listing_filters_to_one_campaigns_work(client):
    mine = a_campaign(client, name="Mine")
    theirs = a_campaign(client, name="Theirs")
    client.post(f"/api/campaigns/{mine['id']}/videos/render", json=custom_payload())
    client.post(f"/api/campaigns/{theirs['id']}/videos/render", json=custom_payload())
    client.post("/api/videos/render", json=custom_payload())

    assert len(client.get("/api/videos").json()) == 3
    assert len(client.get(f"/api/videos?campaign_id={mine['id']}").json()) == 1


def test_a_campaign_video_stream_still_scopes_the_saved_row(client):
    campaign = a_campaign(client)

    body = client.post(
        f"/api/campaigns/{campaign['id']}/videos/render/stream", json=custom_payload()
    ).text
    result = body.splitlines()[-1]

    assert f'"campaign_id": {campaign["id"]}' in result


def test_rendering_into_a_campaign_that_does_not_exist_is_a_404(client):
    assert client.post("/api/campaigns/999/videos/render", json=custom_payload()).status_code == 404
    assert client.get("/api/campaigns/999/video-brief").status_code == 404


# -- the seeded brief ------------------------------------------------------


def test_the_brief_falls_back_to_the_campaign_when_nothing_is_approved(client):
    campaign = a_campaign(client)

    brief = client.get(f"/api/campaigns/{campaign['id']}/video-brief").json()

    assert brief["name"] == "Raya launch — video"
    assert brief["profile"] == "product_marketing"
    assert len(brief["storyboard"]) == 3
    assert brief["storyboard"][0]["headline"] == "Raya launch"
    assert "festive gift set" in brief["storyboard"][1]["body"]


def test_the_brief_leads_with_the_approved_variant(client, session):
    from app.domain import ConceptStatus
    from app.models import Concept, Variant

    campaign = a_campaign(client)
    concept = Concept(
        campaign_id=campaign["id"],
        theme="Gifting made effortless",
        format="video",
        trend_rationale="Gift-set searches are climbing.",
        brand_rationale="The set is already the hero product.",
        variant_count=1,
        variation_axes=["hook"],
        status=ConceptStatus.APPROVED,
    )
    session.add(concept)
    session.flush()
    session.add(
        Variant(
            concept_id=concept.id,
            hook_type="benefit",
            headline="One box, every thank you covered",
            body="The festive set that says it properly.",
            cta="Order the set",
            visual_brief={},
            director_status="pass",
        )
    )
    session.commit()

    brief = client.get(f"/api/campaigns/{campaign['id']}/video-brief").json()

    assert brief["storyboard"][0]["headline"] == "One box, every thank you covered"
    assert brief["storyboard"][1]["headline"] == "Gifting made effortless"
    assert brief["cta"] == "Order the set"
    assert brief["storyboard"][-1]["layout"] == "cta"


def test_deleting_a_campaign_takes_its_videos(client, session):
    from app.models import Campaign, MarketingVideo

    campaign = a_campaign(client)
    client.post(f"/api/campaigns/{campaign['id']}/videos/render", json=custom_payload())

    session.delete(session.get(Campaign, campaign["id"]))
    session.commit()

    assert session.query(MarketingVideo).count() == 0


class TestBrollFlagRoundTrip:
    """The flag lives on the durable brief, so a redo reproduces the same
    video rather than quietly falling back to the deterministic render."""

    def test_it_is_off_unless_asked_for(self, client, studio):
        client.post("/api/videos/render", json={})
        assert studio.seen[-1].use_broll is False

    def test_asking_for_it_reaches_the_studio(self, client, studio):
        client.post("/api/videos/render", json={"use_broll": True})
        assert studio.seen[-1].use_broll is True

    def test_it_is_saved_on_the_video(self, client, session):
        from app.models import MarketingVideo

        created = client.post(
            "/api/videos/render", json={"use_broll": True}
        ).json()
        saved = session.get(MarketingVideo, created["id"])
        assert saved.use_broll is True

    def test_a_redo_keeps_it(self, client, studio):
        created = client.post(
            "/api/videos/render", json={"use_broll": True}
        ).json()
        client.post(f"/api/videos/{created['id']}/redo")
        assert studio.seen[-1].use_broll is True
