import pytest
from fastapi.testclient import TestClient

from app.agents.chat import BriefDraft, ChatAction, ChatTurn
from app.api.deps import get_marketing_chat
from app.db import get_db
from app.domain import CampaignStatus, ConceptStatus
from app.main import app
from app.models import Asset, Campaign, Concept, Variant


class StubStrategist:
    def __init__(self, *turns: ChatTurn):
        self.turns = list(turns)
        self.calls: list[dict] = []

    def respond(self, message, **kwargs):
        self.calls.append({"message": message, **kwargs})
        return self.turns.pop(0)


@pytest.fixture
def strategist():
    return StubStrategist(
        ChatTurn(
            reply="I have turned that into a campaign brief.",
            action=ChatAction.CREATE_CAMPAIGN,
            draft=BriefDraft(name="Embun humidity launch", brief="Launch Embun serum for humid-city commuters."),
        )
    )


@pytest.fixture
def client(session, strategist):
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_marketing_chat] = lambda: strategist
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_a_thread_persists_messages_and_adopts_the_created_campaign(client):
    thread = client.post("/api/conversations", json={"title": "Embun launch"}).json()

    response = client.post(
        f"/api/conversations/{thread['id']}/messages",
        json={"content": "Launch our serum for KL commuters during humid season."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["authorized"] is None
    assert body["campaign"]["name"] == "Embun humidity launch"
    loaded = client.get(f"/api/conversations/{thread['id']}").json()
    assert loaded["campaign_id"] == body["campaign"]["id"]
    assert [message["role"] for message in loaded["messages"]] == [
        "user",
        "assistant",
        "system",
    ]
    assert loaded["messages"][1]["action"] == "create_campaign"


def test_a_default_thread_can_be_created_without_a_request_body(client):
    response = client.post("/api/conversations")

    assert response.status_code == 201
    assert response.json()["title"] == "New strategy"


def test_first_message_replaces_the_placeholder_thread_title(client):
    thread = client.post("/api/conversations", json={}).json()

    client.post(
        f"/api/conversations/{thread['id']}/messages",
        json={"content": "Launch premium nail sets for Merdeka shoppers."},
    )

    loaded = client.get(f"/api/conversations/{thread['id']}").json()
    assert loaded["title"] == "Launch premium nail sets for Merdeka shoppers."


def test_a_partial_model_draft_uses_the_marketers_message_as_its_brief(client, strategist):
    strategist.turns = [
        ChatTurn(
            reply="I have prepared the campaign.",
            action=ChatAction.CREATE_CAMPAIGN,
            draft=BriefDraft(name="Merdeka luxury offer"),
        )
    ]
    thread = client.post("/api/conversations", json={}).json()
    request = "Promote a 31% Merdeka offer for five purchases or more."

    response = client.post(
        f"/api/conversations/{thread['id']}/messages", json={"content": request}
    )

    assert response.status_code == 200
    assert response.json()["campaign"]["brief"] == request


def test_plan_is_authorized_only_from_a_draft_campaign(client, strategist):
    strategist.turns = [ChatTurn(reply="Planning now.", action=ChatAction.RUN_PLAN)]
    campaign = client.post(
        "/api/campaigns", json={"name": "Embun", "brief": "Launch humidity serum."}
    ).json()
    thread = client.post("/api/conversations", json={}).json()
    client.patch(f"/api/conversations/{thread['id']}", json={"campaign_id": campaign["id"]})

    response = client.post(
        f"/api/conversations/{thread['id']}/messages", json={"content": "Go ahead and plan it."}
    )

    assert response.status_code == 200
    assert response.json()["authorized"] == "plan"


def test_an_unsafe_action_becomes_a_system_line_not_an_api_error(client, strategist):
    strategist.turns = [ChatTurn(reply="Generating now.", action=ChatAction.RUN_GENERATE)]
    campaign = client.post(
        "/api/campaigns", json={"name": "Embun", "brief": "Launch humidity serum."}
    ).json()
    thread = client.post("/api/conversations", json={}).json()
    client.patch(f"/api/conversations/{thread['id']}", json={"campaign_id": campaign["id"]})

    response = client.post(
        f"/api/conversations/{thread['id']}/messages", json={"content": "Generate the work."}
    )

    assert response.status_code == 200
    assert response.json()["authorized"] is None
    messages = client.get(f"/api/conversations/{thread['id']}").json()["messages"]
    assert messages[-1]["role"] == "system"
    assert "not ready" in messages[-1]["content"]


def test_listing_threads_keeps_newest_first(client):
    first = client.post("/api/conversations", json={"title": "First"}).json()
    second = client.post("/api/conversations", json={"title": "Second"}).json()

    listed = client.get("/api/conversations").json()

    assert [thread["id"] for thread in listed[:2]] == [second["id"], first["id"]]


def _campaign_with_variant(client, session, *, status=CampaignStatus.GENERATING):
    created = client.post(
        "/api/campaigns", json={"name": "Scripted launch", "brief": "Launch the saved demo."}
    ).json()
    campaign = session.get(Campaign, created["id"])
    campaign.status = status
    concept = Concept(
        campaign_id=campaign.id,
        theme="Saved-media story",
        format="image",
        trend_rationale="Offline demo trend.",
        brand_rationale="Offline demo brand.",
        variant_count=1,
        variation_axes=["hero"],
        status=ConceptStatus.APPROVED,
    )
    session.add(concept)
    session.flush()
    variant = Variant(
        concept_id=concept.id,
        hook_type="hero",
        headline="A saved campaign, ready now",
        body="Reuse the approved library.",
        cta="See the collection",
        visual_brief={
            "composition_notes": "Saved demo composition.",
            "image_prompt": "Saved demo image.",
            "text_placement": "Top left.",
            "placement_zone": "top-left",
            "text_treatment": "bare",
        },
        director_status="pass",
        revision_count=0,
    )
    session.add(variant)
    session.commit()
    return campaign, variant


def _attached_thread(client, campaign_id):
    thread = client.post("/api/conversations", json={}).json()
    client.patch(
        f"/api/conversations/{thread['id']}", json={"campaign_id": campaign_id}
    )
    return thread


def test_the_strategist_can_handoff_a_saved_media_render(client, session, strategist):
    campaign, _ = _campaign_with_variant(client, session)
    thread = _attached_thread(client, campaign.id)
    strategist.turns = [
        ChatTurn(reply="Rendering from the saved library.", action=ChatAction.RUN_RENDER)
    ]

    response = client.post(
        f"/api/conversations/{thread['id']}/messages",
        json={"content": "Continue image generation."},
    )

    assert response.json()["authorized"] == "render"


def test_the_strategist_can_handoff_video_after_image_approval(client, session, strategist):
    campaign, variant = _campaign_with_variant(
        client, session, status=CampaignStatus.READY_TO_PUBLISH
    )
    session.add(
        Asset(
            variant_id=variant.id,
            media_url="/media/saved.png",
            qa_status="passed",
            review_status="approved",
        )
    )
    session.commit()
    thread = _attached_thread(client, campaign.id)
    strategist.turns = [
        ChatTurn(reply="Opening the saved video render.", action=ChatAction.RUN_VIDEO)
    ]

    response = client.post(
        f"/api/conversations/{thread['id']}/messages",
        json={"content": "Generate the campaign video."},
    )

    assert response.json()["authorized"] == "video"


def test_the_strategist_can_open_publish_but_does_not_post(client, session, strategist):
    campaign, variant = _campaign_with_variant(
        client, session, status=CampaignStatus.READY_TO_PUBLISH
    )
    session.add(
        Asset(
            variant_id=variant.id,
            media_url="/media/saved.png",
            qa_status="passed",
            review_status="approved",
        )
    )
    session.commit()
    thread = _attached_thread(client, campaign.id)
    strategist.turns = [
        ChatTurn(reply="Opening Publish previews.", action=ChatAction.OPEN_PUBLISH)
    ]

    response = client.post(
        f"/api/conversations/{thread['id']}/messages",
        json={"content": "Open Publish."},
    )

    assert response.json()["authorized"] == "publish"
    assert session.get(Campaign, campaign.id).status is CampaignStatus.READY_TO_PUBLISH
