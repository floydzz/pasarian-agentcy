"""The narrated runs behind the console.

What matters here is not that the work happens — the blocking routes already
cover that — but that the console can tell a live agent from a finished one, and
that a failure mid-run leaves the campaign somewhere a human can still act.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.agents.base import CrewError
from app.agents.events import AgentEvent
from app.agents.planner import PlanningError
from app.api.deps import get_crew, get_planner
from app.db import get_db
from app.domain import CampaignStatus
from app.main import app
from tests.test_api_campaigns import StubPlanner
from tests.test_api_generation import StubCrew


class NarratingPlanner(StubPlanner):
    def plan(self, brief, *, source_event=None, concept_count=3, sink=None):
        if sink:
            sink(AgentEvent("planner", "started", "Reading the brief"))
            sink(AgentEvent("planner", "finished", "2 grounded concepts"))
        return super().plan(brief, source_event=source_event, concept_count=concept_count)


class NarratingCrew(StubCrew):
    def run(self, concept, *, sink=None):
        if sink:
            sink(AgentEvent("copywriter", "started", "Writing 2 variants"))
            sink(AgentEvent("director", "finished", "Verdict: pass"))
        return super().run(concept)


@pytest.fixture
def planner():
    return NarratingPlanner()


@pytest.fixture
def crew():
    return NarratingCrew()


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


def lines(response) -> list[dict]:
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def of_kind(response, kind: str) -> list[dict]:
    return [line for line in lines(response) if line["kind"] == kind]


class TestNarratedPlanning:
    def test_the_agents_report_themselves_as_they_go(self, client, campaign):
        response = client.post(f"/api/campaigns/{campaign['id']}/plan/stream")

        events = of_kind(response, "event")
        assert [event["detail"] for event in events] == [
            "Reading the brief",
            "2 grounded concepts",
        ]

    def test_events_are_numbered_so_the_console_can_order_them(self, client, campaign):
        response = client.post(f"/api/campaigns/{campaign['id']}/plan/stream")

        assert [event["seq"] for event in of_kind(response, "event")] == [1, 2]

    def test_the_run_ends_with_the_same_plan_the_blocking_route_returns(
        self, client, campaign
    ):
        response = client.post(f"/api/campaigns/{campaign['id']}/plan/stream")

        [result] = of_kind(response, "result")
        assert result["strategy_summary"] == "Lead with the humidity truth."
        assert result["concepts"][0]["status"] == "pending"

    def test_the_plan_is_persisted_by_the_streamed_run(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan/stream")

        concepts = client.get(f"/api/campaigns/{campaign['id']}/concepts").json()
        assert len(concepts) == 1
        assert client.get(f"/api/campaigns/{campaign['id']}").json()["status"] == (
            CampaignStatus.PENDING_PLAN_APPROVAL
        )

    def test_a_failed_run_is_reported_in_the_stream_not_as_a_status_code(
        self, client, campaign, planner
    ):
        planner.error = PlanningError("no concept was grounded")

        response = client.post(f"/api/campaigns/{campaign['id']}/plan/stream")

        # The headers went out before the failure did, so the stream carries it.
        assert response.status_code == 200
        assert of_kind(response, "error")[0]["detail"] == "no concept was grounded"

    def test_a_failed_run_hands_the_campaign_back_as_a_draft(
        self, client, campaign, planner
    ):
        planner.error = PlanningError("boom")

        client.post(f"/api/campaigns/{campaign['id']}/plan/stream")

        assert client.get(f"/api/campaigns/{campaign['id']}").json()["status"] == (
            CampaignStatus.DRAFT
        )

    def test_planning_twice_is_still_refused_up_front(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan/stream")

        assert client.post(f"/api/campaigns/{campaign['id']}/plan/stream").status_code == 409


class TestNarratedGeneration:
    def approve(self, client, campaign) -> None:
        planned = client.post(f"/api/campaigns/{campaign['id']}/plan/stream")
        [result] = of_kind(planned, "result")
        for concept in result["concepts"]:
            client.post(
                f"/api/concepts/{concept['id']}/decision", json={"decision": "approved"}
            )
        client.post(f"/api/campaigns/{campaign['id']}/approve")

    def test_the_crew_narrates_each_agent(self, client, campaign):
        self.approve(client, campaign)

        response = client.post(f"/api/campaigns/{campaign['id']}/generate/stream")

        agents = [event["agent"] for event in of_kind(response, "event")]
        assert agents == ["copywriter", "director"]

    def test_the_run_ends_with_the_variants(self, client, campaign):
        self.approve(client, campaign)

        response = client.post(f"/api/campaigns/{campaign['id']}/generate/stream")

        [result] = of_kind(response, "result")
        assert result["concepts_generated"] == 1
        assert len(result["variants"]) == 2

    def test_the_variants_are_persisted_by_the_streamed_run(self, client, campaign):
        self.approve(client, campaign)
        client.post(f"/api/campaigns/{campaign['id']}/generate/stream")

        assert len(client.get(f"/api/campaigns/{campaign['id']}/variants").json()) == 2

    def test_a_crew_failure_reaches_the_console_as_an_event_and_an_error(
        self, client, campaign, crew
    ):
        self.approve(client, campaign)
        crew.error = CrewError("copywriter returned 1 variant, which needs 2")

        response = client.post(f"/api/campaigns/{campaign['id']}/generate/stream")

        failures = [e for e in of_kind(response, "event") if e["phase"] == "failed"]
        assert "copywriter returned 1 variant" in failures[0]["detail"]

    def test_a_crew_failure_leaves_the_campaign_where_a_retry_can_reach_it(
        self, client, campaign, crew
    ):
        self.approve(client, campaign)
        crew.error = CrewError("boom")

        client.post(f"/api/campaigns/{campaign['id']}/generate/stream")

        assert client.get(f"/api/campaigns/{campaign['id']}").json()["status"] == (
            CampaignStatus.GENERATING
        )

    def test_generation_is_still_refused_before_the_plan_is_approved(
        self, client, campaign
    ):
        client.post(f"/api/campaigns/{campaign['id']}/plan/stream")

        response = client.post(f"/api/campaigns/{campaign['id']}/generate/stream")

        assert response.status_code == 409
