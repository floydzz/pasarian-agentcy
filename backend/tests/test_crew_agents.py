"""The three generation agents, each exercised on its own.

The graph that joins them is tested separately in `test_crew.py`.
"""

import pytest

from app.agents.base import CrewError
from app.agents.copywriter import CopyDraft, CopySet, Copywriter
from app.agents.director import UNEXPLAINED, Director, DirectorVerdict
from app.agents.visual_planner import VisualDraft, VisualPlanner, VisualSet
from app.domain import Concept
from app.rag.store import Retrieved


class FakeProvider:
    """Records what an agent asked for and replays canned responses in order."""

    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def structured(self, *, system: str, prompt: str, schema):
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def make_concept(**overrides) -> Concept:
    defaults = dict(
        concept_id="c-1",
        theme="Reapplication, humidity edition",
        format="image",
        trend_rationale="Reapplication demos are surging. [sources: tiktok.md#0-a]",
        brand_rationale="Humidity-first positioning. [sources: brand.md#0-b]",
        variant_count=2,
        variation_axes=["emotional hook", "cta phrasing"],
    )
    return Concept(**{**defaults, **overrides})


BRAND_CONTEXT = [
    Retrieved(
        chunk_id="brand.md#0-b",
        text="Warm bilingual Manglish. We never promise whitening or fairness.",
        heading="Brand voice",
        source="brand.md",
        distance=0.1,
    )
]


def copy_draft(**overrides) -> CopyDraft:
    defaults = dict(
        hook_type="emotional hook",
        headline="Pukul 3 petang, muka dah kilat?",
        body="The 2pm shine is humidity, not you. Embun keeps pores clear.",
        cta="Shop the serum",
    )
    return CopyDraft(**{**defaults, **overrides})


def visual_draft(**overrides) -> VisualDraft:
    defaults = dict(
        composition_notes="Eye lands on the face, headline in the sky negative space.",
        image_prompt='A Malaysian woman on an LRT platform, "Pukul 3 petang" in the sky.',
        text_placement="Headline upper third, CTA bottom-right on a solid band.",
    )
    return VisualDraft(**{**defaults, **overrides})


class TestCopywriter:
    def test_one_variant_is_written_per_variation_axis(self):
        provider = FakeProvider(
            CopySet(
                variants=[
                    copy_draft(hook_type="emotional hook"),
                    copy_draft(hook_type="cta phrasing"),
                ]
            )
        )

        written = Copywriter(provider=provider).write(
            make_concept(), brand_context=BRAND_CONTEXT
        )

        assert [draft.hook_type for draft in written] == [
            "emotional hook",
            "cta phrasing",
        ]

    def test_the_axes_reach_the_prompt(self):
        provider = FakeProvider(
            CopySet(variants=[copy_draft(), copy_draft(hook_type="cta phrasing")])
        )

        Copywriter(provider=provider).write(make_concept(), brand_context=BRAND_CONTEXT)

        prompt = provider.calls[0]["prompt"]
        assert "emotional hook" in prompt and "cta phrasing" in prompt

    def test_the_brand_kb_is_the_stated_ground_truth(self):
        provider = FakeProvider(
            CopySet(variants=[copy_draft(), copy_draft(hook_type="cta phrasing")])
        )

        Copywriter(provider=provider).write(make_concept(), brand_context=BRAND_CONTEXT)

        assert "never promise whitening" in provider.calls[0]["prompt"]
        assert "ground truth" in provider.calls[0]["system"].lower()

    def test_a_wrong_variant_count_breaks_the_diversity_promise_and_fails(self):
        provider = FakeProvider(CopySet(variants=[copy_draft()]))

        with pytest.raises(CrewError, match="one per variation axis"):
            Copywriter(provider=provider).write(
                make_concept(), brand_context=BRAND_CONTEXT
            )

    def test_an_unrecognised_axis_label_is_snapped_to_its_position(self):
        provider = FakeProvider(
            CopySet(
                variants=[
                    copy_draft(hook_type="feelings!"),
                    copy_draft(hook_type="cta phrasing"),
                ]
            )
        )

        written = Copywriter(provider=provider).write(
            make_concept(), brand_context=BRAND_CONTEXT
        )

        assert written[0].hook_type == "emotional hook"

    def test_revision_notes_are_passed_back_to_the_writer(self):
        provider = FakeProvider(
            CopySet(variants=[copy_draft(), copy_draft(hook_type="cta phrasing")])
        )

        Copywriter(provider=provider).write(
            make_concept(),
            brand_context=BRAND_CONTEXT,
            revision_notes="Variant 2 repeats variant 1.",
        )

        assert "Variant 2 repeats variant 1." in provider.calls[0]["prompt"]

    def test_a_first_pass_carries_no_revision_notes(self):
        provider = FakeProvider(
            CopySet(variants=[copy_draft(), copy_draft(hook_type="cta phrasing")])
        )

        Copywriter(provider=provider).write(make_concept(), brand_context=BRAND_CONTEXT)

        assert "DIRECTOR'S NOTES" not in provider.calls[0]["prompt"]


class TestVisualPlanner:
    def test_the_actual_copy_text_is_what_gets_planned_around(self):
        provider = FakeProvider(VisualSet(briefs=[visual_draft(), visual_draft()]))
        copy = [copy_draft(), copy_draft(hook_type="cta phrasing", headline="Kilat lagi?")]

        VisualPlanner(provider=provider).plan(
            make_concept(), copy, brand_context=BRAND_CONTEXT
        )

        prompt = provider.calls[0]["prompt"]
        assert "Pukul 3 petang, muka dah kilat?" in prompt
        assert "Kilat lagi?" in prompt
        assert "Shop the serum" in prompt

    def test_one_brief_is_planned_per_copy_variant(self):
        provider = FakeProvider(VisualSet(briefs=[visual_draft(), visual_draft()]))

        briefs = VisualPlanner(provider=provider).plan(
            make_concept(), [copy_draft(), copy_draft()], brand_context=BRAND_CONTEXT
        )

        assert len(briefs) == 2

    def test_a_missing_brief_fails_rather_than_leaving_a_variant_unplanned(self):
        provider = FakeProvider(VisualSet(briefs=[visual_draft()]))

        with pytest.raises(CrewError, match="exactly one"):
            VisualPlanner(provider=provider).plan(
                make_concept(),
                [copy_draft(), copy_draft()],
                brand_context=BRAND_CONTEXT,
            )

    def test_the_planner_is_told_the_copy_is_fixed(self):
        provider = FakeProvider(VisualSet(briefs=[visual_draft()]))

        VisualPlanner(provider=provider).plan(
            make_concept(), [copy_draft()], brand_context=BRAND_CONTEXT
        )

        assert "never rewrite it" in provider.calls[0]["system"].lower()


class TestDirector:
    def test_copy_and_visuals_are_reviewed_as_pairs(self):
        provider = FakeProvider(DirectorVerdict(verdict="pass"))

        Director(provider=provider).review(
            make_concept(),
            [copy_draft()],
            [visual_draft()],
            brand_context=BRAND_CONTEXT,
        )

        prompt = provider.calls[0]["prompt"]
        assert "Pukul 3 petang, muka dah kilat?" in prompt
        assert "Headline upper third" in prompt

    def test_the_promised_axes_are_shown_so_diversity_can_be_checked(self):
        provider = FakeProvider(DirectorVerdict(verdict="pass"))

        Director(provider=provider).review(
            make_concept(),
            [copy_draft()],
            [visual_draft()],
            brand_context=BRAND_CONTEXT,
        )

        assert "emotional hook, cta phrasing" in provider.calls[0]["prompt"]

    def test_a_passing_verdict_carries_no_notes(self):
        provider = FakeProvider(DirectorVerdict(verdict="pass", notes="looks nice"))

        verdict = Director(provider=provider).review(
            make_concept(), [copy_draft()], [visual_draft()], brand_context=[]
        )

        assert verdict.notes == ""

    def test_a_revision_verdict_keeps_its_notes(self):
        provider = FakeProvider(
            DirectorVerdict(verdict="revise_copy", notes="Variant 2 repeats variant 1.")
        )

        verdict = Director(provider=provider).review(
            make_concept(), [copy_draft()], [visual_draft()], brand_context=[]
        )

        assert verdict.verdict == "revise_copy"
        assert verdict.notes == "Variant 2 repeats variant 1."

    def test_an_unexplained_revision_still_gives_the_next_agent_something(self):
        provider = FakeProvider(DirectorVerdict(verdict="revise_visuals", notes="  "))

        verdict = Director(provider=provider).review(
            make_concept(), [copy_draft()], [visual_draft()], brand_context=[]
        )

        assert verdict.notes == UNEXPLAINED
