import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.domain import CampaignStatus, ConceptStatus
from app.models import Asset, Campaign, Concept, Variant


def _campaign(session, **over):
    campaign = Campaign(
        name="Raya glow launch",
        brief="Push the hydrating serum to MY women 25-34 before Raya.",
        **over,
    )
    session.add(campaign)
    session.flush()
    return campaign


class TestSchema:
    def test_creates_all_four_pipeline_tables(self, engine):
        tables = set(inspect(engine).get_table_names())
        assert {"campaigns", "concepts", "variants", "assets"} <= tables


class TestCampaign:
    def test_new_campaign_starts_as_draft(self, session):
        assert _campaign(session).status is CampaignStatus.DRAFT

    def test_auto_mode_is_off_by_default(self, session):
        campaign = _campaign(session)
        assert campaign.auto_approve_plan is False
        assert campaign.auto_approve_assets is False

    def test_status_round_trips_as_the_enum(self, session):
        campaign = _campaign(session, status=CampaignStatus.PENDING_PLAN_APPROVAL)
        session.expire_all()
        loaded = session.get(Campaign, campaign.id)
        assert loaded.status is CampaignStatus.PENDING_PLAN_APPROVAL


class TestConcept:
    def test_variation_axes_round_trip_as_a_list(self, session):
        campaign = _campaign(session)
        axes = ["emotional hook", "specific detail emphasized", "cta phrasing"]
        concept = Concept(
            campaign_id=campaign.id,
            theme="Glass skin in 90% humidity",
            format="image",
            trend_rationale="trend: #glassskin",
            brand_rationale="kb: warm bilingual voice",
            variant_count=3,
            variation_axes=axes,
        )
        session.add(concept)
        session.flush()
        session.expire_all()
        assert session.get(Concept, concept.id).variation_axes == axes

    def test_concept_starts_pending_review(self, session):
        campaign = _campaign(session)
        concept = Concept(
            campaign_id=campaign.id, theme="t", format="image",
            trend_rationale="a", brand_rationale="b",
            variant_count=1, variation_axes=["hook"],
        )
        session.add(concept)
        session.flush()
        assert concept.status is ConceptStatus.PENDING

    def test_concept_requires_a_campaign(self, session):
        session.add(Concept(
            campaign_id=999_999, theme="t", format="image",
            trend_rationale="a", brand_rationale="b",
            variant_count=1, variation_axes=["hook"],
        ))
        with pytest.raises(IntegrityError):
            session.flush()


class TestCascade:
    def _full_chain(self, session):
        campaign = _campaign(session)
        concept = Concept(
            campaign_id=campaign.id, theme="t", format="image",
            trend_rationale="a", brand_rationale="b",
            variant_count=1, variation_axes=["hook"],
        )
        session.add(concept)
        session.flush()
        variant = Variant(
            concept_id=concept.id, hook_type="hook", headline="h",
            body="b", cta="c",
            visual_brief={"composition_notes": "n", "image_prompt": "p",
                          "text_placement": "t",
                          "placement_zone": "top-left"},
        )
        session.add(variant)
        session.flush()
        asset = Asset(variant_id=variant.id, media_url="file:///tmp/a.png")
        session.add(asset)
        session.flush()
        return campaign, concept, variant, asset

    def test_deleting_a_campaign_removes_its_whole_tree(self, session):
        campaign, _, _, _ = self._full_chain(session)
        session.delete(campaign)
        session.flush()
        assert session.scalars(select(Concept)).all() == []
        assert session.scalars(select(Variant)).all() == []
        assert session.scalars(select(Asset)).all() == []

    def test_relationships_navigate_the_whole_chain(self, session):
        campaign, _, _, asset = self._full_chain(session)
        session.expire_all()
        loaded = session.get(Campaign, campaign.id)
        assert loaded.concepts[0].variants[0].assets[0].id == asset.id

    def test_asset_starts_flagged_and_pending(self, session):
        _, _, _, asset = self._full_chain(session)
        assert asset.qa_status == "flagged"
        assert asset.review_status == "pending"

    def test_variant_starts_flagged_until_the_director_passes_it(self, session):
        _, _, variant, _ = self._full_chain(session)
        assert variant.director_status == "flagged"
