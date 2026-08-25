import pytest
from fastapi.testclient import TestClient

from app.agents.base import CrewError
from app.agents.crew import CrewResult
from app.api.deps import get_crew, get_planner
from app.db import get_db
from app.domain import CampaignStatus, ConceptStatus, Variant, VisualBrief
from app.main import app
from tests.test_api_campaigns import StubPlanner, make_concept


def make_variant(concept_id: str, hook_type: str, **overrides) -> Variant:
    defaults = dict(
        variant_id=f"v-{concept_id}-{hook_type}",
        concept_id=concept_id,
        hook_type=hook_type,
        headline="Pukul 3 petang, muka dah kilat?",
        body="The 2pm shine is humidity, not you.",
        cta="Shop the serum",
        visual_brief=VisualBrief(
            composition_notes="Face centre, headline in the sky.",
            image_prompt='LRT platform, "Pukul 3 petang" in the sky.',
            text_placement="Headline upper third, CTA bottom-right.",
            placement_zone="top-left",
        ),
        director_status="pass",
        director_notes=None,
    )
    return Variant(**{**defaults, **overrides})


class StubCrew:
    """Stands in for the LangGraph crew — records the concepts it was asked to run."""

    def __init__(self, *, error: Exception | None = None, **variant_overrides) -> None:
        self.error = error
        self.variant_overrides = variant_overrides
        self.ran: list[str] = []
        self.revisions = 0

    def run(self, concept, *, sink=None) -> CrewResult:
        self.ran.append(concept.theme)
        if self.error:
            raise self.error
        return CrewResult(
            variants=[
                make_variant(concept.concept_id, axis, **self.variant_overrides)
                for axis in concept.variation_axes
            ],
            revisions=self.revisions,
        )


@pytest.fixture
def planner():
    return StubPlanner()


@pytest.fixture
def crew():
    return StubCrew()


@pytest.fixture
def client(session, planner, crew):
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_planner] = lambda: planner
    app.dependency_overrides[get_crew] = lambda: crew
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def campaign(client):
    return client.post(
        "/api/campaigns",
        json={"name": "Merdeka 2026", "brief": "Push the serum for Merdeka."},
    ).json()


def approved_campaign(client, campaign) -> dict:
    """Walk a campaign through planning and the gate, the manual way."""
    planned = client.post(f"/api/campaigns/{campaign['id']}/plan").json()
    for concept in planned["concepts"]:
        client.post(
            f"/api/concepts/{concept['id']}/decision", json={"decision": "approved"}
        )
    client.post(f"/api/campaigns/{campaign['id']}/approve")
    return planned


class TestAutoMode:
    def test_a_campaign_starts_with_both_gates_manual(self, client, campaign):
        assert campaign["auto_approve_plan"] is False
        assert campaign["auto_approve_assets"] is False

    def test_either_toggle_can_be_set_on_its_own(self, client, campaign):
        response = client.patch(
            f"/api/campaigns/{campaign['id']}/auto-mode",
            json={"auto_approve_plan": True},
        )

        body = response.json()
        assert body["auto_approve_plan"] is True
        assert body["auto_approve_assets"] is False

    def test_both_gates_take_the_same_shape(self, client, campaign):
        response = client.patch(
            f"/api/campaigns/{campaign['id']}/auto-mode",
            json={"auto_approve_plan": True, "auto_approve_assets": True},
        )

        body = response.json()
        assert body["auto_approve_plan"] is True
        assert body["auto_approve_assets"] is True

    def test_auto_mode_carries_the_plan_straight_past_the_gate(self, client, campaign):
        client.patch(
            f"/api/campaigns/{campaign['id']}/auto-mode",
            json={"auto_approve_plan": True},
        )

        client.post(f"/api/campaigns/{campaign['id']}/plan")

        fetched = client.get(f"/api/campaigns/{campaign['id']}").json()
        assert fetched["status"] == CampaignStatus.GENERATING

    def test_auto_approved_concepts_are_marked_approved_not_merely_skipped(
        self, client, campaign
    ):
        client.patch(
            f"/api/campaigns/{campaign['id']}/auto-mode",
            json={"auto_approve_plan": True},
        )

        planned = client.post(f"/api/campaigns/{campaign['id']}/plan").json()

        assert all(c["status"] == ConceptStatus.APPROVED for c in planned["concepts"])

    def test_manual_mode_still_stops_at_the_gate(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan")

        fetched = client.get(f"/api/campaigns/{campaign['id']}").json()
        assert fetched["status"] == CampaignStatus.PENDING_PLAN_APPROVAL


class TestGeneration:
    def test_the_crew_runs_over_the_approved_concepts(self, client, campaign, crew):
        approved_campaign(client, campaign)

        response = client.post(f"/api/campaigns/{campaign['id']}/generate")

        assert response.status_code == 200
        assert crew.ran == ["Reapplication, humidity edition"]

    def test_one_variant_is_persisted_per_variation_axis(self, client, campaign):
        approved_campaign(client, campaign)

        body = client.post(f"/api/campaigns/{campaign['id']}/generate").json()

        assert body["concepts_generated"] == 1
        assert [v["hook_type"] for v in body["variants"]] == ["hook", "cta"]

    def test_variants_are_retrievable_afterwards(self, client, campaign):
        approved_campaign(client, campaign)
        client.post(f"/api/campaigns/{campaign['id']}/generate")

        variants = client.get(f"/api/campaigns/{campaign['id']}/variants").json()

        assert len(variants) == 2
        assert variants[0]["visual_brief"]["image_prompt"].startswith("LRT platform")

    def test_generation_cannot_run_before_the_plan_is_approved(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan")

        response = client.post(f"/api/campaigns/{campaign['id']}/generate")

        assert response.status_code == 409
        assert "approved" in response.json()["detail"]

    def test_a_rejected_concept_never_reaches_the_crew(self, client, campaign, planner, crew):
        planner.concepts = [make_concept("Keep this"), make_concept("Drop this")]
        planned = client.post(f"/api/campaigns/{campaign['id']}/plan").json()
        client.post(
            f"/api/concepts/{planned['concepts'][0]['id']}/decision",
            json={"decision": "approved"},
        )
        client.post(
            f"/api/concepts/{planned['concepts'][1]['id']}/decision",
            json={"decision": "rejected", "edit_note": "Too close to last Raya."},
        )
        client.post(f"/api/campaigns/{campaign['id']}/approve")

        client.post(f"/api/campaigns/{campaign['id']}/generate")

        assert crew.ran == ["Keep this"]

    def test_rerunning_generation_resumes_instead_of_duplicating(self, client, campaign, crew):
        approved_campaign(client, campaign)
        client.post(f"/api/campaigns/{campaign['id']}/generate")

        body = client.post(f"/api/campaigns/{campaign['id']}/generate").json()

        assert body["concepts_generated"] == 0
        assert body["concepts_skipped"] == 1
        assert len(client.get(f"/api/campaigns/{campaign['id']}/variants").json()) == 2
        assert crew.ran == ["Reapplication, humidity edition"]

    def test_an_unknown_campaign_has_no_variants_to_list(self, client):
        assert client.get("/api/campaigns/9999/variants").status_code == 404


class TestDirectorVerdictsSurvivePersistence:
    def test_a_passing_variant_is_stored_clean(self, client, campaign):
        approved_campaign(client, campaign)

        body = client.post(f"/api/campaigns/{campaign['id']}/generate").json()

        assert body["variants"][0]["director_status"] == "pass"
        assert body["variants"][0]["director_notes"] is None

    def test_a_flagged_variant_reaches_the_human_with_its_notes(self, client, campaign, crew):
        crew.variant_overrides = {
            "director_status": "flagged",
            "director_notes": "Variant 2 repeats variant 1.",
        }
        crew.revisions = 2
        approved_campaign(client, campaign)

        body = client.post(f"/api/campaigns/{campaign['id']}/generate").json()

        assert body["variants"][0]["director_status"] == "flagged"
        assert body["variants"][0]["director_notes"] == "Variant 2 repeats variant 1."

    def test_the_revision_count_is_recorded_against_the_variant(self, client, campaign, crew):
        crew.revisions = 2
        approved_campaign(client, campaign)

        body = client.post(f"/api/campaigns/{campaign['id']}/generate").json()

        assert body["variants"][0]["revision_count"] == 2


class TestGenerationFailure:
    def test_a_crew_failure_is_reported_rather_than_swallowed(self, client, campaign, crew):
        crew.error = CrewError("copywriter returned 1 variant, which needs 2")
        approved_campaign(client, campaign)

        response = client.post(f"/api/campaigns/{campaign['id']}/generate")

        assert response.status_code == 502
        assert "copywriter" in response.json()["detail"]

    def test_a_failed_run_leaves_the_campaign_where_a_retry_can_reach_it(
        self, client, campaign, crew
    ):
        crew.error = CrewError("boom")
        approved_campaign(client, campaign)
        client.post(f"/api/campaigns/{campaign['id']}/generate")

        fetched = client.get(f"/api/campaigns/{campaign['id']}").json()
        assert fetched["status"] == CampaignStatus.GENERATING
