import pytest
from fastapi.testclient import TestClient

from app.agents.base import CrewError
from app.api.deps import get_crew, get_planner
from app.db import get_db
from app.main import app
from app.models import Campaign, Run
from tests.test_api_campaigns import StubPlanner, make_concept
from tests.test_api_generation import StubCrew


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
        json={"name": "Raya 2026 — serum", "brief": "Push the serum through Raya."},
    ).json()


def approve_and_release(client, campaign_id: int) -> None:
    for concept in client.get(f"/api/campaigns/{campaign_id}/concepts").json():
        client.post(
            f"/api/concepts/{concept['id']}/decision", json={"decision": "approved"}
        )
    client.post(f"/api/campaigns/{campaign_id}/approve")


class TestRecordingAPlan:
    def test_a_planning_pass_is_recorded(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        runs = client.get("/api/runs").json()
        assert len(runs) == 1
        assert runs[0]["kind"] == "plan"
        assert runs[0]["status"] == "succeeded"

    def test_the_summary_counts_what_the_pass_produced(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        run = client.get("/api/runs").json()[0]
        assert run["concepts"] == 1
        assert run["summary"] == "1 grounded concept proposed"

    def test_several_concepts_are_counted_in_the_plural(self, session, campaign):
        planner = StubPlanner(concepts=[make_concept("One"), make_concept("Two")])
        app.dependency_overrides[get_planner] = lambda: planner
        with TestClient(app) as client:
            client.post(f"/api/campaigns/{campaign['id']}/plan")
            run = client.get("/api/runs").json()[0]
        assert run["summary"] == "2 grounded concepts proposed"

    def test_the_events_are_kept_so_the_run_can_be_reopened(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        run_id = client.get("/api/runs").json()[0]["id"]
        detail = client.get(f"/api/runs/{run_id}").json()
        assert detail["events"]
        assert all("agent" in event and "detail" in event for event in detail["events"])

    def test_the_list_route_leaves_the_events_out(self, client, campaign):
        """A history page must not download every event of every run to render."""
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        assert "events" not in client.get("/api/runs").json()[0]

    def test_the_provider_is_recorded_against_the_run(self, client, campaign):
        """A plan the offline provider wrote must never be mistaken for a model's."""
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        assert client.get("/api/runs").json()[0]["provider"]


class TestTimestampsCarryTheirZone:
    """MySQL DATETIME has no zone, so the API has to supply one.

    Sent unmarked, an ISO string with no offset is parsed by a browser as local
    time — and a run recorded a second ago on a UTC container then renders as
    eight hours old in Kuala Lumpur. This only shows up once the app is
    containerised, which is exactly why it is pinned here.
    """

    def test_a_run_timestamp_is_marked_utc(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        started = client.get("/api/runs").json()[0]["started_at"]
        assert started.endswith("Z") or "+00:00" in started

    def test_a_campaign_timestamp_is_marked_utc(self, client, campaign):
        assert campaign["created_at"].endswith("Z") or "+00:00" in campaign["created_at"]

    def test_a_scrape_timestamp_is_marked_utc(self, client):
        client.get("/api/trends/sources")
        client.post("/api/trends/scrape")
        scraped = client.get("/api/trends/sources").json()[0]["last_scraped_at"]
        assert scraped.endswith("Z") or "+00:00" in scraped

    def test_a_never_scraped_keyword_has_no_timestamp_to_stamp(self, client):
        assert client.get("/api/trends/sources").json()[0]["last_scraped_at"] is None


class TestRecordingTheCrew:
    def test_a_crew_run_is_recorded_with_its_counts(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        approve_and_release(client, campaign["id"])
        client.post(f"/api/campaigns/{campaign['id']}/generate")

        run = client.get("/api/runs").json()[0]
        assert run["kind"] == "generate"
        assert run["concepts"] == 1
        assert run["variants"] > 0

    def test_flagged_work_is_named_in_the_summary(self, client, campaign, crew):
        """It is the thing anyone scanning history is actually looking for."""
        crew.variant_overrides = {
            "director_status": "flagged",
            "director_notes": "Two variants say the same thing.",
        }
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        approve_and_release(client, campaign["id"])
        client.post(f"/api/campaigns/{campaign['id']}/generate")

        run = client.get("/api/runs").json()[0]
        assert run["flagged"] == run["variants"] > 0
        assert "flagged for you" in run["summary"]

    def test_a_clean_run_says_so(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        approve_and_release(client, campaign["id"])
        client.post(f"/api/campaigns/{campaign['id']}/generate")
        assert "all passed" in client.get("/api/runs").json()[0]["summary"]


class TestRecordingAFailure:
    def test_a_failed_crew_run_is_recorded_rather_than_lost(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        approve_and_release(client, campaign["id"])

        app.dependency_overrides[get_crew] = lambda: StubCrew(
            error=CrewError("copywriter returned 2 variants for a 3-axis concept")
        )
        client.post(f"/api/campaigns/{campaign['id']}/generate")

        run = client.get("/api/runs").json()[0]
        assert run["status"] == "failed"
        assert "3-axis concept" in run["error"]

    def test_a_failed_run_still_carries_its_summary(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        approve_and_release(client, campaign["id"])
        app.dependency_overrides[get_crew] = lambda: StubCrew(error=CrewError("boom"))
        client.post(f"/api/campaigns/{campaign['id']}/generate")
        assert client.get("/api/runs").json()[0]["summary"] == "boom"


class TestReadingHistory:
    def test_runs_come_back_newest_first(self, client, campaign):
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        approve_and_release(client, campaign["id"])
        client.post(f"/api/campaigns/{campaign['id']}/generate")

        runs = client.get("/api/runs").json()
        assert [run["kind"] for run in runs] == ["generate", "plan"]

    def test_history_can_be_narrowed_to_one_campaign(self, client, campaign):
        other = client.post(
            "/api/campaigns", json={"name": "Merdeka", "brief": "Merdeka push."}
        ).json()
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        client.post(f"/api/campaigns/{other['id']}/plan")

        runs = client.get(f"/api/runs?campaign_id={campaign['id']}").json()
        assert len(runs) == 1
        assert runs[0]["campaign_id"] == campaign["id"]

    def test_an_unknown_run_is_a_404(self, client):
        assert client.get("/api/runs/9999").status_code == 404

    def test_history_outlives_the_campaign_it_records(self, client, campaign, session):
        """“What did the machine do last Tuesday” stays answerable afterwards."""
        client.post(f"/api/campaigns/{campaign['id']}/plan")
        session.delete(session.get(Campaign, campaign["id"]))
        session.commit()

        run = session.query(Run).one()
        assert run.campaign_id is None
        assert run.campaign_name == "Raya 2026 — serum"
