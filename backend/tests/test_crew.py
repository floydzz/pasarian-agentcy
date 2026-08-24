"""The LangGraph generation crew — the cycle, its bound, and what falls out.

These tests drive the graph through real `Copywriter`/`VisualPlanner`/`Director`
objects and only fake the provider, so the routing being tested is the routing
that runs in production.
"""

import pytest

from app.agents.copywriter import CopySet, Copywriter
from app.agents.crew import MAX_REVISIONS, GenerationCrew
from app.agents.director import Director, DirectorVerdict
from app.agents.visual_planner import VisualPlanner, VisualSet
from app.rag.store import KnowledgeStore
from tests.test_crew_agents import copy_draft, make_concept, visual_draft
from tests.test_store import local_embedder

BRAND_DOC = """# Brand voice

Warm bilingual Manglish. We never promise whitening or fairness.

## Hero product

The Embun hydrating serum targets humidity-clogged pores.
"""


@pytest.fixture
def store(tmp_path):
    store = KnowledgeStore(path=tmp_path / "chroma", embedder=local_embedder)
    store.ingest_company_kb(BRAND_DOC, source="brand.md")
    return store


class ScriptedProvider:
    """Answers each agent from its own script, keyed by the schema requested.

    A copy/visual script shorter than the number of calls repeats its last
    entry, so a test only has to script the passes it actually cares about.
    """

    def __init__(self, *, copy=None, visuals=None, verdicts) -> None:
        self.copy = list(copy or [CopySet(variants=[copy_draft(), copy_draft()])])
        self.visuals = list(
            visuals or [VisualSet(briefs=[visual_draft(), visual_draft()])]
        )
        self.verdicts = list(verdicts)
        self.calls: list[str] = []

    def structured(self, *, system: str, prompt: str, schema):
        self.calls.append(schema.__name__)
        if schema is CopySet:
            return self.copy.pop(0) if len(self.copy) > 1 else self.copy[0]
        if schema is VisualSet:
            return self.visuals.pop(0) if len(self.visuals) > 1 else self.visuals[0]
        return self.verdicts.pop(0) if len(self.verdicts) > 1 else self.verdicts[0]


def build_crew(store, provider, **overrides) -> GenerationCrew:
    return GenerationCrew(
        copywriter=Copywriter(provider=provider),
        visual_planner=VisualPlanner(provider=provider),
        director=Director(provider=provider),
        store=store,
        **overrides,
    )


def passing() -> DirectorVerdict:
    return DirectorVerdict(verdict="pass")


def revise_copy(notes="Variant 2 repeats variant 1.") -> DirectorVerdict:
    return DirectorVerdict(verdict="revise_copy", notes=notes)


def revise_visuals(notes="No room for the CTA in variant 1.") -> DirectorVerdict:
    return DirectorVerdict(verdict="revise_visuals", notes=notes)


class TestTheHappyPath:
    def test_the_agents_run_in_order(self, store):
        provider = ScriptedProvider(verdicts=[passing()])

        build_crew(store, provider).run(make_concept())

        assert provider.calls == ["CopySet", "VisualSet", "DirectorVerdict"]

    def test_a_passing_run_produces_one_variant_per_axis(self, store):
        provider = ScriptedProvider(verdicts=[passing()])

        result = build_crew(store, provider).run(make_concept())

        assert len(result.variants) == 2
        assert result.revisions == 0
        assert result.passed

    def test_a_passing_variant_carries_no_director_notes(self, store):
        provider = ScriptedProvider(verdicts=[passing()])

        variant = build_crew(store, provider).run(make_concept()).variants[0]

        assert variant.director_status == "pass"
        assert variant.director_notes is None

    def test_copy_and_visuals_are_paired_onto_the_variant(self, store):
        provider = ScriptedProvider(verdicts=[passing()])

        variant = build_crew(store, provider).run(make_concept()).variants[0]

        assert variant.headline == "Pukul 3 petang, muka dah kilat?"
        assert variant.visual_brief.text_placement.startswith("Headline upper third")

    def test_variants_are_tied_to_their_concept_with_distinct_ids(self, store):
        provider = ScriptedProvider(verdicts=[passing()])

        variants = build_crew(store, provider).run(make_concept()).variants

        assert {v.concept_id for v in variants} == {"c-1"}
        assert variants[0].variant_id != variants[1].variant_id

    def test_the_brand_kb_is_retrieved_and_shown_to_every_agent(self, store):
        provider = ScriptedProvider(verdicts=[passing()])
        prompts = []
        original = provider.structured

        def spy(*, system, prompt, schema):
            prompts.append(prompt)
            return original(system=system, prompt=prompt, schema=schema)

        provider.structured = spy
        build_crew(store, provider).run(make_concept())

        assert all("whitening" in prompt for prompt in prompts)


class TestTheRevisionCycle:
    def test_revise_copy_re_enters_at_the_copywriter(self, store):
        provider = ScriptedProvider(verdicts=[revise_copy(), passing()])

        result = build_crew(store, provider).run(make_concept())

        assert provider.calls == [
            "CopySet",
            "VisualSet",
            "DirectorVerdict",
            "CopySet",
            "VisualSet",
            "DirectorVerdict",
        ]
        assert result.revisions == 1

    def test_revise_visuals_leaves_the_copy_alone(self, store):
        provider = ScriptedProvider(verdicts=[revise_visuals(), passing()])

        build_crew(store, provider).run(make_concept())

        assert provider.calls == [
            "CopySet",
            "VisualSet",
            "DirectorVerdict",
            "VisualSet",
            "DirectorVerdict",
        ]

    def test_the_director_notes_reach_the_agent_being_sent_back_to(self, store):
        provider = ScriptedProvider(verdicts=[revise_copy("Too close to last Raya."), passing()])
        prompts = []
        original = provider.structured

        def spy(*, system, prompt, schema):
            prompts.append((schema.__name__, prompt))
            return original(system=system, prompt=prompt, schema=schema)

        provider.structured = spy
        build_crew(store, provider).run(make_concept())

        second_copy_pass = [p for name, p in prompts if name == "CopySet"][1]
        assert "Too close to last Raya." in second_copy_pass

    def test_a_run_that_passes_after_revision_is_not_flagged(self, store):
        provider = ScriptedProvider(verdicts=[revise_copy(), passing()])

        result = build_crew(store, provider).run(make_concept())

        assert result.passed
        assert result.variants[0].director_notes is None


class TestTheRevisionBudget:
    def test_a_stubborn_director_cannot_loop_forever(self, store):
        provider = ScriptedProvider(verdicts=[revise_copy()])

        result = build_crew(store, provider).run(make_concept())

        assert result.revisions == MAX_REVISIONS
        assert provider.calls.count("DirectorVerdict") == MAX_REVISIONS + 1

    def test_work_that_runs_out_of_budget_falls_through_flagged(self, store):
        provider = ScriptedProvider(verdicts=[revise_copy("Still the same idea.")])

        result = build_crew(store, provider).run(make_concept())

        assert not result.passed
        assert all(v.director_status == "flagged" for v in result.variants)

    def test_a_flagged_variant_tells_the_human_what_the_director_objected_to(self, store):
        provider = ScriptedProvider(verdicts=[revise_visuals("CTA falls off the frame.")])

        result = build_crew(store, provider).run(make_concept())

        assert result.variants[0].director_notes == "CTA falls off the frame."

    def test_the_budget_is_configurable_and_respected(self, store):
        provider = ScriptedProvider(verdicts=[revise_copy()])

        result = build_crew(store, provider, max_revisions=1).run(make_concept())

        assert result.revisions == 1
        assert provider.calls.count("DirectorVerdict") == 2
