import pytest
from pydantic import ValidationError

from app.domain import (
    CampaignStatus,
    Concept,
    ConceptStatus,
    Variant,
    VisualBrief,
    Asset,
    CalendarEvent,
    can_transition,
    next_status,
)


class TestCampaignStateMachine:
    def test_draft_advances_to_planning(self):
        assert next_status(CampaignStatus.DRAFT) is CampaignStatus.PLANNING

    def test_full_happy_path_reaches_published(self):
        status = CampaignStatus.DRAFT
        seen = [status]
        while (nxt := next_status(status)) is not None:
            status = nxt
            seen.append(status)
        assert seen == [
            CampaignStatus.DRAFT,
            CampaignStatus.PLANNING,
            CampaignStatus.PENDING_PLAN_APPROVAL,
            CampaignStatus.GENERATING,
            CampaignStatus.PENDING_ASSET_REVIEW,
            CampaignStatus.READY_TO_PUBLISH,
            CampaignStatus.PUBLISHED,
        ]

    def test_published_is_terminal(self):
        assert next_status(CampaignStatus.PUBLISHED) is None

    def test_cannot_skip_a_stage(self):
        assert not can_transition(CampaignStatus.DRAFT, CampaignStatus.GENERATING)

    def test_cannot_move_backwards(self):
        assert not can_transition(
            CampaignStatus.GENERATING, CampaignStatus.PLANNING
        )


class TestConcept:
    def _valid(self, **over):
        base = dict(
            concept_id="c1",
            theme="Glass skin for the humid tropics",
            format="image",
            trend_rationale="trend chunk: #glassskin surging on TikTok MY",
            brand_rationale="kb chunk: brand voice is warm, bilingual",
            variant_count=3,
            variation_axes=["emotional hook", "specific detail", "cta phrasing"],
        )
        base.update(over)
        return base

    def test_defaults_to_pending_status(self):
        assert Concept(**self._valid()).status is ConceptStatus.PENDING

    def test_variant_count_must_match_number_of_variation_axes(self):
        with pytest.raises(ValidationError, match="variation_axes"):
            Concept(**self._valid(variant_count=5))

    def test_rejects_unknown_format(self):
        with pytest.raises(ValidationError):
            Concept(**self._valid(format="billboard"))

    def test_rejects_empty_variation_axes(self):
        with pytest.raises(ValidationError):
            Concept(**self._valid(variant_count=0, variation_axes=[]))


class TestVariant:
    def _valid(self, **over):
        base = dict(
            variant_id="v1",
            concept_id="c1",
            hook_type="emotional hook",
            headline="Kulit kaca, cuaca Malaysia.",
            body="Lightweight hydration that survives 90% humidity.",
            cta="Shop the serum",
            visual_brief={
                "composition_notes": "close-up, soft window light",
                "image_prompt": "a dewy face in soft light, product bottle right third",
                "text_placement": "headline upper-left, CTA lower-right",
                "placement_zone": "top-left",
                "text_treatment": "bare",
            },
        )
        base.update(over)
        return base

    def test_director_status_defaults_to_flagged_until_reviewed(self):
        assert Variant(**self._valid()).director_status == "flagged"

    def test_visual_brief_requires_an_image_prompt(self):
        brief = {"composition_notes": "x", "text_placement": "y"}
        with pytest.raises(ValidationError):
            Variant(**self._valid(visual_brief=brief))


class TestAsset:
    def test_defaults_to_pending_review_and_flagged_qa(self):
        asset = Asset(asset_id="a1", variant_id="v1", media_url="file:///tmp/a1.png")
        assert asset.review_status == "pending"
        assert asset.qa_status == "flagged"
        assert asset.qa_notes is None


class TestCalendarEvent:
    def test_parses_iso_date(self):
        ev = CalendarEvent(
            event_id="e1",
            name="Hari Raya Aidilfitri",
            date="2027-03-20",
            lookahead_days=21,
            suggested_tone="warm, family, balik kampung",
        )
        assert ev.date.year == 2027 and ev.date.month == 3


def test_visual_brief_requires_a_placement_zone():
    with pytest.raises(ValidationError):
        VisualBrief(
            composition_notes="notes",
            image_prompt="prompt",
            text_placement="upper third",
        )


def test_visual_brief_rejects_a_zone_outside_the_grid():
    with pytest.raises(ValidationError):
        VisualBrief(
            composition_notes="notes",
            image_prompt="prompt",
            text_placement="upper third",
            placement_zone="upper-third",
        )


def test_visual_brief_accepts_a_grid_zone():
    brief = VisualBrief(
        composition_notes="notes",
        image_prompt="prompt",
        text_placement="upper third",
        placement_zone="top-left",
    )
    assert brief.placement_zone == "top-left"
    assert brief.text_treatment == "glass-panel"


def test_visual_brief_rejects_an_unknown_text_treatment():
    with pytest.raises(ValidationError):
        VisualBrief(
            composition_notes="notes",
            image_prompt="prompt",
            text_placement="upper third",
            placement_zone="top-left",
            text_treatment="opaque-card",
        )
