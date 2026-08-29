import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.agents.studio import Studio
from app.agents.vision_qa import QAVerdict
from app.api.deps import get_crew, get_planner, get_studio
from app.db import get_db
from app.domain import CampaignStatus, Concept
from app.main import app
from app.media.demo import DemoMediaProvider
from app.media.storage import AssetStorage
from tests.test_api_generation import StubCrew, StubPlanner


class PassingQA:
    """Stands in for the vision agent — the redo loop is covered in test_studio."""

    def review(self, image, *, headline, cta, brief) -> QAVerdict:
        return QAVerdict(status="passed", notes="")


def three_axis_concept() -> Concept:
    return Concept(
        concept_id="concept-raya",
        theme="Raya, priced for the moment",
        format="image",
        trend_rationale="Raya bundles are surging. [sources: tiktok.md#0-a]",
        brand_rationale="Humidity-first positioning. [sources: brand.md#0-b]",
        variant_count=3,
        variation_axes=["hook", "proof", "cta"],
    )


@pytest.fixture
def storage(tmp_path):
    return AssetStorage(tmp_path)


@pytest.fixture
def studio(storage):
    return Studio(provider=DemoMediaProvider(), qa=PassingQA(), storage=storage)


@pytest.fixture
def client(session, studio):
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_planner] = lambda: StubPlanner(
        concepts=[three_axis_concept()]
    )
    app.dependency_overrides[get_crew] = lambda: StubCrew()
    app.dependency_overrides[get_studio] = lambda: studio
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def campaign_pending_plan(client):
    """Planned, but nobody has been through the gate yet."""
    campaign = client.post(
        "/api/campaigns",
        json={"name": "Raya 2027", "brief": "Push the Raya bundle."},
    ).json()
    client.post(f"/api/campaigns/{campaign['id']}/plan")
    return _Campaign(campaign["id"])


@pytest.fixture
def campaign_with_variants(client):
    """Walked all the way to GENERATING with three variants persisted."""
    campaign = client.post(
        "/api/campaigns",
        json={"name": "Raya 2027", "brief": "Push the Raya bundle."},
    ).json()
    planned = client.post(f"/api/campaigns/{campaign['id']}/plan").json()
    for concept in planned["concepts"]:
        client.post(
            f"/api/concepts/{concept['id']}/decision", json={"decision": "approved"}
        )
    client.post(f"/api/campaigns/{campaign['id']}/approve")
    client.post(f"/api/campaigns/{campaign['id']}/generate")
    return _Campaign(campaign["id"])


class _Campaign:
    """Just an id, in the attribute shape the tests read it in."""

    def __init__(self, id: int) -> None:
        self.id = id


# -- rendering -------------------------------------------------------------


def test_render_rejects_a_campaign_that_has_not_generated(client, campaign_pending_plan):
    response = client.post(f"/api/campaigns/{campaign_pending_plan.id}/render")
    assert response.status_code == 409


def test_render_produces_one_asset_per_variant(client, campaign_with_variants):
    response = client.post(f"/api/campaigns/{campaign_with_variants.id}/render")
    assert response.status_code == 200

    body = response.json()
    assert body["variants_rendered"] == 3
    assert len(body["assets"]) == 3
    assert all(asset["media_url"].startswith("/media/") for asset in body["assets"])


def test_render_advances_the_campaign_to_asset_review(client, campaign_with_variants):
    client.post(f"/api/campaigns/{campaign_with_variants.id}/render")
    campaign = client.get(f"/api/campaigns/{campaign_with_variants.id}").json()
    assert campaign["status"] == CampaignStatus.PENDING_ASSET_REVIEW


def test_rendering_twice_skips_what_is_already_rendered(client, campaign_with_variants):
    client.post(f"/api/campaigns/{campaign_with_variants.id}/render")
    second = client.post(f"/api/campaigns/{campaign_with_variants.id}/render")
    assert second.status_code == 200
    assert second.json()["variants_rendered"] == 0
    assert second.json()["variants_skipped"] == 3


def test_the_rendered_bytes_are_a_real_creative(client, campaign_with_variants, storage):
    asset = client.post(
        f"/api/campaigns/{campaign_with_variants.id}/render"
    ).json()["assets"][0]
    assert storage.read(asset["media_url"])[:8] == b"\x89PNG\r\n\x1a\n"


# -- the gate --------------------------------------------------------------


def test_approving_an_asset_records_the_decision(client, campaign_with_variants):
    asset_id = client.post(
        f"/api/campaigns/{campaign_with_variants.id}/render"
    ).json()["assets"][0]["id"]

    response = client.post(f"/api/assets/{asset_id}/approve")
    assert response.status_code == 200
    assert response.json()["review_status"] == "approved"


def test_rejecting_an_asset_records_the_decision(client, campaign_with_variants):
    asset_id = client.post(
        f"/api/campaigns/{campaign_with_variants.id}/render"
    ).json()["assets"][0]["id"]

    assert client.post(f"/api/assets/{asset_id}/reject").json()["review_status"] == "rejected"


def test_closing_the_gate_needs_at_least_one_approved_asset(client, campaign_with_variants):
    client.post(f"/api/campaigns/{campaign_with_variants.id}/render")
    response = client.post(f"/api/campaigns/{campaign_with_variants.id}/assets/approve")
    assert response.status_code == 409


def test_closing_the_gate_advances_to_ready_to_publish(client, campaign_with_variants):
    assets = client.post(f"/api/campaigns/{campaign_with_variants.id}/render").json()["assets"]
    client.post(f"/api/assets/{assets[0]['id']}/approve")

    response = client.post(f"/api/campaigns/{campaign_with_variants.id}/assets/approve")
    assert response.status_code == 200
    assert response.json()["status"] == CampaignStatus.READY_TO_PUBLISH


def test_auto_mode_approves_qa_passed_assets_and_skips_the_gate(client, campaign_with_variants):
    client.patch(
        f"/api/campaigns/{campaign_with_variants.id}/auto-mode",
        json={"auto_approve_assets": True},
    )
    client.post(f"/api/campaigns/{campaign_with_variants.id}/render")

    campaign = client.get(f"/api/campaigns/{campaign_with_variants.id}").json()
    assert campaign["status"] == CampaignStatus.READY_TO_PUBLISH


def test_render_writes_a_history_row(client, campaign_with_variants):
    client.post(f"/api/campaigns/{campaign_with_variants.id}/render")
    kinds = [run["kind"] for run in client.get("/api/runs").json()]
    assert "render" in kinds


def test_redo_replaces_one_asset(client, campaign_with_variants):
    asset = client.post(f"/api/campaigns/{campaign_with_variants.id}/render").json()["assets"][0]
    response = client.post(f"/api/assets/{asset['id']}/redo")

    assert response.status_code == 200
    assert response.json()["media_url"] != asset["media_url"]


def test_a_redone_asset_goes_back_to_pending_review(client, campaign_with_variants):
    asset = client.post(f"/api/campaigns/{campaign_with_variants.id}/render").json()["assets"][0]
    client.post(f"/api/assets/{asset['id']}/approve")

    assert client.post(f"/api/assets/{asset['id']}/redo").json()["review_status"] == "pending"


def test_a_redo_does_not_leave_the_superseded_file_behind(
    client, campaign_with_variants, storage
):
    asset = client.post(f"/api/campaigns/{campaign_with_variants.id}/render").json()["assets"][0]
    client.post(f"/api/assets/{asset['id']}/redo")

    assert not storage.path_for(asset["media_url"]).exists()


def test_listing_assets_returns_them_for_the_gate(client, campaign_with_variants):
    client.post(f"/api/campaigns/{campaign_with_variants.id}/render")
    listed = client.get(f"/api/campaigns/{campaign_with_variants.id}/assets").json()
    assert len(listed) == 3


def test_streaming_a_render_narrates_it_and_ends_with_the_result(
    client, campaign_with_variants
):
    body = client.post(f"/api/campaigns/{campaign_with_variants.id}/render/stream").text
    lines = [line for line in body.splitlines() if line]

    assert '"kind": "event"' in lines[0]
    assert '"variants_rendered": 3' in lines[-1]


class TestTheGateHoldsUntilTheWorkIsActuallyDone:
    """Auto-mode waives the *asking*, not the finishing.

    A waived gate means "do not stop to ask me about creatives that passed" —
    it has never meant "declare the campaign shipped regardless". Two things
    can still be outstanding when a render pass ends: variants nothing was
    rendered for, because the pass was capped or broke off part way, and
    creatives QA flagged, which auto-mode deliberately leaves undecided.

    Advancing past either one strands the campaign. `READY_TO_PUBLISH` is not
    in `RENDERABLE`, so the unrendered variants can never be picked up, and the
    flagged creatives are left pending behind a gate that is closed for good.
    Observed on a live campaign on 2026-08-26: 8 creatives of 18 variants, 3
    auto-approved, 5 flagged, and a console offering no button at all.
    """

    class FlagsEverythingAfterTheFirst:
        def __init__(self) -> None:
            self.seen = 0

        def review(self, image, *, headline, cta, brief) -> QAVerdict:
            self.seen += 1
            if self.seen == 1:
                return QAVerdict(status="passed", notes="")
            return QAVerdict(status="flagged", notes="The type sits on her face.")

    @pytest.fixture
    def picky(self, session, storage):
        """A client whose QA passes the first creative and flags the rest."""
        studio = Studio(
            provider=DemoMediaProvider(),
            qa=self.FlagsEverythingAfterTheFirst(),
            storage=storage,
        )
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_planner] = lambda: StubPlanner(
            concepts=[three_axis_concept()]
        )
        app.dependency_overrides[get_crew] = lambda: StubCrew()
        app.dependency_overrides[get_studio] = lambda: studio
        with TestClient(app) as test_client:
            yield test_client
        app.dependency_overrides.clear()

    def test_a_flagged_creative_keeps_the_gate_open(self, picky):
        campaign = picky.post(
            "/api/campaigns", json={"name": "Raya 2027", "brief": "Push it."}
        ).json()
        planned = picky.post(f"/api/campaigns/{campaign['id']}/plan").json()
        for concept in planned["concepts"]:
            picky.post(
                f"/api/concepts/{concept['id']}/decision", json={"decision": "approved"}
            )
        picky.post(f"/api/campaigns/{campaign['id']}/approve")
        picky.post(f"/api/campaigns/{campaign['id']}/generate")
        picky.patch(
            f"/api/campaigns/{campaign['id']}/auto-mode",
            json={"auto_approve_assets": True},
        )

        picky.post(f"/api/campaigns/{campaign['id']}/render")

        status = picky.get(f"/api/campaigns/{campaign['id']}").json()["status"]
        assert status == CampaignStatus.PENDING_ASSET_REVIEW

    def test_an_unrendered_variant_keeps_the_gate_open(
        self, client, campaign_with_variants, monkeypatch
    ):
        """A capped or part-finished pass leaves variants with no creative.

        The campaign has to stay renderable so the next pass can pick them up.
        """
        monkeypatch.setattr(
            "app.api.assets.get_settings",
            lambda: _capped_at(1),
        )
        client.patch(
            f"/api/campaigns/{campaign_with_variants.id}/auto-mode",
            json={"auto_approve_assets": True},
        )

        client.post(f"/api/campaigns/{campaign_with_variants.id}/render")

        status = client.get(f"/api/campaigns/{campaign_with_variants.id}").json()[
            "status"
        ]
        assert status == CampaignStatus.PENDING_ASSET_REVIEW

    def test_the_rest_can_still_be_rendered_afterwards(
        self, client, campaign_with_variants, monkeypatch
    ):
        """The point of holding the gate: the remaining work is still reachable."""
        monkeypatch.setattr(
            "app.api.assets.get_settings", lambda: _capped_at(1)
        )
        client.patch(
            f"/api/campaigns/{campaign_with_variants.id}/auto-mode",
            json={"auto_approve_assets": True},
        )
        client.post(f"/api/campaigns/{campaign_with_variants.id}/render")

        monkeypatch.undo()
        client.post(f"/api/campaigns/{campaign_with_variants.id}/render")

        assets = client.get(
            f"/api/campaigns/{campaign_with_variants.id}/assets"
        ).json()
        assert len(assets) == 3


def _capped_at(cap: int):
    """The real settings with only the render cap lowered."""
    from app.config import get_settings

    return get_settings().model_copy(update={"max_renders_per_run": cap})


class TestVariantsAreRenderedAtTheSameTime:
    """A render is a vendor image call and then a vision call, per variant.

    Nothing is shared between them. Eight rendered one after another measured
    913s on 2026-08-27 — eight waits for one pass of work. The fan-out is
    narrower than the crew's on purpose: these are metered image jobs, and a
    rate-limited pass fails having spent the quota rather than made creatives.
    """

    class SlowStudio:
        """A studio that waits like a vendor and records the overlap."""

        def __init__(self, inner: Studio, *, delay: float = 0.15) -> None:
            self.inner = inner
            self.delay = delay
            self.live = 0
            self.peak = 0
            self._guard = threading.Lock()

        def run(self, spec, *, sink=None):
            with self._guard:
                self.live += 1
                self.peak = max(self.peak, self.live)
            try:
                time.sleep(self.delay)
                return self.inner.run(spec, sink=sink)
            finally:
                with self._guard:
                    self.live -= 1

    @pytest.fixture
    def slow(self, session, storage):
        studio = self.SlowStudio(
            Studio(provider=DemoMediaProvider(), qa=PassingQA(), storage=storage)
        )
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_planner] = lambda: StubPlanner(
            concepts=[three_axis_concept()]
        )
        app.dependency_overrides[get_crew] = lambda: StubCrew()
        app.dependency_overrides[get_studio] = lambda: studio
        with TestClient(app) as test_client:
            yield test_client, studio
        app.dependency_overrides.clear()

    def _campaign(self, client) -> int:
        campaign = client.post(
            "/api/campaigns", json={"name": "R", "brief": "b"}
        ).json()
        planned = client.post(f"/api/campaigns/{campaign['id']}/plan").json()
        for concept in planned["concepts"]:
            client.post(
                f"/api/concepts/{concept['id']}/decision",
                json={"decision": "approved"},
            )
        client.post(f"/api/campaigns/{campaign['id']}/approve")
        client.post(f"/api/campaigns/{campaign['id']}/generate")
        return campaign["id"]

    def test_more_than_one_variant_is_in_flight(self, slow):
        client, studio = slow
        client.post(f"/api/campaigns/{self._campaign(client)}/render")
        assert studio.peak > 1

    def test_three_variants_take_about_as_long_as_one(self, slow):
        client, _ = slow
        campaign_id = self._campaign(client)

        started = time.time()
        client.post(f"/api/campaigns/{campaign_id}/render")
        elapsed = time.time() - started

        # Three 0.15s renders: ~0.15s overlapped, ~0.45s sequential.
        assert elapsed < 0.35

    def test_every_variant_still_gets_a_creative(self, slow):
        """Speed that loses work is not speed."""
        client, _ = slow
        campaign_id = self._campaign(client)

        body = client.post(f"/api/campaigns/{campaign_id}/render").json()

        variants = client.get(f"/api/campaigns/{campaign_id}/variants").json()
        assert body["variants_rendered"] == len(variants)

    def test_creatives_stay_in_variant_order(self, slow):
        """A fast render finishing first must not reshuffle the campaign."""
        client, _ = slow
        campaign_id = self._campaign(client)
        client.post(f"/api/campaigns/{campaign_id}/render")

        assets = client.get(f"/api/campaigns/{campaign_id}/assets").json()
        variant_ids = [row["variant_id"] for row in assets]
        assert variant_ids == sorted(variant_ids)
