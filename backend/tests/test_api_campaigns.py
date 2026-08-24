import pytest
from fastapi.testclient import TestClient

from app.agents.events import AgentEvent
from app.agents.planner import PlanningError, PlanResult
from app.api.deps import get_planner
from app.db import get_db
from app.domain import CampaignStatus, Concept, ConceptStatus
from app.main import app


def make_concept(theme: str = "Reapplication, humidity edition") -> Concept:
    return Concept(
        concept_id=f"concept-{theme.lower().replace(' ', '-')}",
        theme=theme,
        format="video",
        trend_rationale="Reapplication demos are surging. [sources: tiktok.md#0-a]",
        brand_rationale="Humidity-first positioning. [sources: brand.md#0-b]",
        variant_count=2,
        variation_axes=["hook", "cta"],
    )


class StubPlanner:
    def __init__(self, *, concepts=None, error: Exception | None = None) -> None:
        self.concepts = concepts if concepts is not None else [make_concept()]
        self.error = error
        self.briefs: list[str] = []
        self.notes: list[str] = []
        self.revised: Concept | None = None

    def plan(self, brief, *, source_event=None, concept_count=3, sink=None):
        self.briefs.append(brief)
        # The real agent narrates itself as it works, and the recording of a
        # run depends on that, so the stub does it too — including before it
        # fails, which is the case where the events matter most.
        if sink is not None:
            sink(AgentEvent("planner", "started", "Reading the brief"))
        if self.error:
            raise self.error
        if sink is not None:
            sink(
                AgentEvent(
                    "planner",
                    "finished",
                    f"{len(self.concepts)} grounded concepts ready for review",
                )
            )
        return PlanResult(
            strategy_summary="Lead with the humidity truth.",
            concepts=self.concepts,
            company_context=[],
            trend_context=[],
        )

    def revise(self, brief, concept, note):
        self.notes.append(note)
        if self.error:
            raise self.error
        reworked = self.revised or make_concept("Reworked")
        return reworked.model_copy(
            update={"concept_id": concept.concept_id, "status": ConceptStatus.EDITED}
        )


@pytest.fixture
def planner():
    return StubPlanner()


@pytest.fixture
def client(session, planner):
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_planner] = lambda: planner
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def campaign(client):
    response = client.post(
        "/api/campaigns",
        json={"name": "Merdeka 2026", "brief": "Push the serum for Merdeka."},
    )
    return response.json()


class TestHealth:
    def test_health_reports_ok(self, client):
        assert client.get("/api/health").json()["status"] == "ok"


class TestCreatingCampaigns:
    def test_a_new_campaign_starts_as_a_draft(self, client):
        response = client.post(
            "/api/campaigns", json={"name": "Merdeka 2026", "brief": "Serum push."}
        )
        assert response.status_code == 201
        assert response.json()["status"] == CampaignStatus.DRAFT

    def test_a_blank_brief_is_rejected(self, client):
        response = client.post("/api/campaigns", json={"name": "X", "brief": "  "})
        assert response.status_code == 422

    def test_campaigns_can_be_listed_and_fetched(self, client, campaign):
        assert any(c["id"] == campaign["id"] for c in client.get("/api/campaigns").json())
        assert client.get(f"/api/campaigns/{campaign['id']}").json()["name"] == "Merdeka 2026"

    def test_an_unknown_campaign_is_a_404(self, client):
        assert client.get("/api/campaigns/9999").status_code == 404


class TestPlanning:
    def test_planning_returns_concepts_awaiting_approval(self, client, campaign):
        response = client.post(f"/api/campaigns/{campaign['id']}/plan")

        assert response.status_code == 200
        body = response.json()
        assert body["strategy_summary"]
        assert body["concepts"][0]["status"] == ConceptStatus.PENDING

    def test_planning_moves_the_campaign_to_the_approval_gate(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        fetched = client.get(f"/api/campaigns/{campaign['id']}").json()
        assert fetched["status"] == CampaignStatus.PENDING_PLAN_APPROVAL

    def test_the_brief_is_what_gets_planned(self, client, campaign, planner):
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        assert planner.briefs == ["Push the serum for Merdeka."]

    def test_concepts_are_persisted_and_retrievable(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        concepts = client.get(f"/api/campaigns/{campaign['id']}/concepts").json()
        assert concepts[0]["variation_axes"] == ["hook", "cta"]

    def test_replanning_an_already_planned_campaign_is_refused(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        assert client.post(f"/api/campaigns/{campaign['id']}/plan").status_code == 409

    def test_a_planner_failure_leaves_the_campaign_editable(self, client, session, planner):
        planner.error = PlanningError("no concept was grounded")
        created = client.post(
            "/api/campaigns", json={"name": "X", "brief": "Something vague."}
        ).json()

        response = client.post(f"/api/campaigns/{created['id']}/plan")

        assert response.status_code == 502
        assert "grounded" in response.json()["detail"]
        assert client.get(f"/api/campaigns/{created['id']}").json()["status"] == (
            CampaignStatus.DRAFT
        )


class TestApprovalGate:
    def test_a_concept_can_be_approved(self, client, campaign):
        planned = client.post(f"/api/campaigns/{campaign['id']}/plan").json()
        concept_id = planned["concepts"][0]["id"]

        response = client.post(f"/api/concepts/{concept_id}/decision", json={"decision": "approved"})

        assert response.json()["status"] == ConceptStatus.APPROVED

    def test_a_rejection_can_carry_an_edit_note(self, client, campaign):
        planned = client.post(f"/api/campaigns/{campaign['id']}/plan").json()
        concept_id = planned["concepts"][0]["id"]

        response = client.post(
            f"/api/concepts/{concept_id}/decision",
            json={"decision": "rejected", "edit_note": "Too close to last Raya."},
        )

        assert response.json()["edit_note"] == "Too close to last Raya."

    def test_approving_the_plan_requires_an_approved_concept(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan")

        response = client.post(f"/api/campaigns/{campaign['id']}/approve")

        assert response.status_code == 409
        assert "approved concept" in response.json()["detail"]

    def test_approving_the_plan_opens_generation(self, client, campaign):
        planned = client.post(f"/api/campaigns/{campaign['id']}/plan").json()
        client.post(
            f"/api/concepts/{planned['concepts'][0]['id']}/decision",
            json={"decision": "approved"},
        )

        response = client.post(f"/api/campaigns/{campaign['id']}/approve")

        assert response.json()["status"] == CampaignStatus.GENERATING

    def test_a_draft_campaign_cannot_skip_to_approval(self, client, campaign):
        assert client.post(f"/api/campaigns/{campaign['id']}/approve").status_code == 409


class TestTheEditHandoff:
    def test_an_edit_reworks_the_concept_in_place(self, client, campaign, planner):
        planned = client.post(f"/api/campaigns/{campaign['id']}/plan").json()
        concept_id = planned["concepts"][0]["id"]
        planner.revised = make_concept("Night routine, humidity edition")

        response = client.post(
            f"/api/concepts/{concept_id}/revise",
            json={"note": "Make it about night routines."},
        )

        body = response.json()
        assert body["id"] == concept_id
        assert body["theme"] == "Night routine, humidity edition"

    def test_an_edited_concept_waits_to_be_looked_at_again(self, client, campaign, planner):
        planned = client.post(f"/api/campaigns/{campaign['id']}/plan").json()
        planner.revised = make_concept("Reworked")

        response = client.post(
            f"/api/concepts/{planned['concepts'][0]['id']}/revise",
            json={"note": "Softer tone."},
        )

        assert response.json()["status"] == ConceptStatus.EDITED
        assert response.json()["edit_note"] == "Softer tone."

    def test_the_note_is_what_reaches_the_planner(self, client, campaign, planner):
        planned = client.post(f"/api/campaigns/{campaign['id']}/plan").json()
        planner.revised = make_concept("Reworked")

        client.post(
            f"/api/concepts/{planned['concepts'][0]['id']}/revise",
            json={"note": "Drop the LRT setting."},
        )

        assert planner.notes == ["Drop the LRT setting."]

    def test_a_blank_note_is_rejected(self, client, campaign):
        planned = client.post(f"/api/campaigns/{campaign['id']}/plan").json()

        response = client.post(
            f"/api/concepts/{planned['concepts'][0]['id']}/revise", json={"note": "   "}
        )

        assert response.status_code == 422

    def test_an_ungrounded_rework_leaves_the_original_standing(self, client, campaign, planner):
        planned = client.post(f"/api/campaigns/{campaign['id']}/plan").json()
        concept_id = planned["concepts"][0]["id"]
        planner.error = PlanningError("the rework cites no company knowledge")

        response = client.post(
            f"/api/concepts/{concept_id}/revise", json={"note": "Promise whitening."}
        )

        assert response.status_code == 502
        fetched = client.get(f"/api/campaigns/{campaign['id']}/concepts").json()[0]
        assert fetched["theme"] == "Reapplication, humidity edition"
        assert fetched["status"] == ConceptStatus.PENDING

    def test_an_edit_is_too_late_once_the_plan_is_approved(self, client, campaign):
        planned = client.post(f"/api/campaigns/{campaign['id']}/plan").json()
        concept_id = planned["concepts"][0]["id"]
        client.post(f"/api/concepts/{concept_id}/decision", json={"decision": "approved"})
        client.post(f"/api/campaigns/{campaign['id']}/approve")

        response = client.post(
            f"/api/concepts/{concept_id}/revise", json={"note": "Too late."}
        )

        assert response.status_code == 409

    def test_an_unknown_concept_is_a_404(self, client):
        assert client.post("/api/concepts/9999/revise", json={"note": "x"}).status_code == 404
