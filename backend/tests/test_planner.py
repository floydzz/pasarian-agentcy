import pytest

from app.agents.planner import (
    CampaignPlan,
    ConceptDraft,
    PlanningAgent,
    PlanningError,
)
from app.domain import Concept, ConceptStatus
from app.rag.ingest import COMPANY_KB_DIR, TRENDS_DIR, ingest_directory
from app.rag.store import COMPANY_KB, TREND_CORPUS, KnowledgeStore
from tests.test_store import local_embedder

BRAND_DOC = """# Brand voice

Warm bilingual Manglish. We never promise whitening or fairness.

## Hero product

The Embun hydrating serum targets humidity-clogged pores.
"""

TREND_DOC = """# TikTok Malaysia

Sunscreen reapplication demos are surging among MY viewers.

## Shopee

Serum bundles trending ahead of the 9.9 sale.
"""


@pytest.fixture
def store(tmp_path):
    store = KnowledgeStore(path=tmp_path / "chroma", embedder=local_embedder)
    store.ingest_company_kb(BRAND_DOC, source="brand.md")
    store.ingest_trends(TREND_DOC, source="tiktok.md")
    return store


def draft(**overrides) -> ConceptDraft:
    defaults = dict(
        theme="Reapplication, humidity edition",
        format="video",
        trend_rationale="Reapplication demos are surging in MY.",
        brand_rationale="Sits on our humidity-first positioning.",
        variant_count=3,
        variation_axes=["hook", "setting", "cta"],
        brand_citations=[],
        trend_citations=[],
    )
    return ConceptDraft(**{**defaults, **overrides})


def test_draft_uses_the_explicit_variation_axes_as_its_variant_count():
    planned = draft(variant_count=5, variation_axes=["hook", "setting"])

    assert planned.variant_count == 2


class FakeProvider:
    """Records what the agent asked for and replays a canned plan."""

    def __init__(self, plan: CampaignPlan) -> None:
        self.plan = plan
        self.calls: list[dict] = []

    def structured(self, *, system: str, prompt: str, schema):
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        return self.plan


@pytest.fixture
def agent(store):
    def build(plan: CampaignPlan) -> tuple[PlanningAgent, FakeProvider]:
        provider = FakeProvider(plan)
        return PlanningAgent(provider=provider, store=store), provider

    return build


def cited(store) -> tuple[str, str]:
    brand = store.retrieve_company("humidity serum pores", k=1)[0].chunk_id
    trend = store.retrieve_trends("sunscreen reapplication", k=1)[0].chunk_id
    return brand, trend


class TestContextAssembly:
    def test_the_brief_is_carried_into_the_prompt(self, store, agent):
        brand, trend = cited(store)
        planner, provider = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[draft(brand_citations=[brand], trend_citations=[trend])],
            )
        )

        planner.plan("Merdeka campaign for the hydrating serum")

        assert "Merdeka campaign for the hydrating serum" in provider.calls[0]["prompt"]

    def test_both_corpora_reach_the_prompt_under_distinct_roles(self, store, agent):
        brand, trend = cited(store)
        planner, provider = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[draft(brand_citations=[brand], trend_citations=[trend])],
            )
        )

        planner.plan("serum campaign for humid weather and reapplication")
        prompt = provider.calls[0]["prompt"]

        assert "brand.md" in prompt and "tiktok.md" in prompt
        assert prompt.index("COMPANY KNOWLEDGE") < prompt.index("TREND SIGNALS")

    def test_the_system_prompt_ranks_the_sources(self, store, agent):
        brand, trend = cited(store)
        planner, provider = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[draft(brand_citations=[brand], trend_citations=[trend])],
            )
        )

        planner.plan("serum campaign")
        system = provider.calls[0]["system"].lower()

        assert "ground truth" in system
        assert "inspiration" in system

    def test_the_prompt_repeats_the_exact_output_contract_for_model_fallbacks(
        self, store, agent
    ):
        brand, trend = cited(store)
        planner, provider = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[draft(brand_citations=[brand], trend_citations=[trend])],
            )
        )

        planner.plan("serum campaign")
        prompt = provider.calls[0]["prompt"]

        assert '"strategy_summary"' in prompt
        assert '"brand_citations"' in prompt
        assert "concept_id" in prompt

    def test_the_provider_is_asked_for_the_plan_schema(self, store, agent):
        brand, trend = cited(store)
        planner, provider = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[draft(brand_citations=[brand], trend_citations=[trend])],
            )
        )

        planner.plan("serum campaign")

        assert provider.calls[0]["schema"] is CampaignPlan

    def test_an_empty_brief_is_refused(self, store, agent):
        planner, _ = agent(CampaignPlan(strategy_summary="s", concepts=[draft()]))
        with pytest.raises(ValueError, match="brief"):
            planner.plan("   ")


class TestConceptOutput:
    def test_drafts_become_domain_concepts_awaiting_approval(self, store, agent):
        brand, trend = cited(store)
        planner, _ = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[draft(brand_citations=[brand], trend_citations=[trend])],
            )
        )

        concepts = planner.plan("serum campaign").concepts

        assert concepts[0].status is ConceptStatus.PENDING
        assert concepts[0].concept_id
        assert concepts[0].theme == "Reapplication, humidity edition"

    def test_every_concept_gets_a_distinct_id(self, store, agent):
        brand, trend = cited(store)
        planner, _ = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[
                    draft(brand_citations=[brand], trend_citations=[trend]),
                    draft(theme="Second", brand_citations=[brand], trend_citations=[trend]),
                ],
            )
        )

        concepts = planner.plan("serum campaign").concepts

        assert concepts[0].concept_id != concepts[1].concept_id

    def test_the_citations_are_written_into_the_rationales(self, store, agent):
        brand, trend = cited(store)
        planner, _ = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[draft(brand_citations=[brand], trend_citations=[trend])],
            )
        )

        concept = planner.plan("serum campaign").concepts[0]

        assert brand in concept.brand_rationale
        assert trend in concept.trend_rationale

    def test_the_calendar_event_is_recorded_as_provenance(self, store, agent):
        brand, trend = cited(store)
        planner, _ = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[draft(brand_citations=[brand], trend_citations=[trend])],
            )
        )

        concept = planner.plan("serum campaign", source_event="Merdeka").concepts[0]

        assert concept.provenance == "Merdeka"


class TestCitationsAreVerified:
    def test_an_invented_citation_is_stripped(self, store, agent):
        brand, trend = cited(store)
        planner, _ = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[
                    draft(
                        brand_citations=[brand, "brand.md#99-deadbeef"],
                        trend_citations=[trend],
                    )
                ],
            )
        )

        concept = planner.plan("serum campaign").concepts[0]

        assert "deadbeef" not in concept.brand_rationale

    def test_a_concept_with_no_real_brand_citation_fails_planning(self, store, agent):
        _, trend = cited(store)
        planner, _ = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[
                    draft(
                        theme="Ungrounded idea",
                        brand_citations=["brand.md#99-deadbeef"],
                        trend_citations=[trend],
                    )
                ],
            )
        )

        with pytest.raises(PlanningError, match="Ungrounded idea"):
            planner.plan("serum campaign")

    def test_a_citation_echoed_with_the_brackets_it_was_shown_in_still_counts(
        self, store, agent
    ):
        """`render_context` presents each id as `[id]`, and a model reading
        "use ids exactly as given" copies the brackets too. Verified against
        qwen3.7-plus on 2026-08-26, where it cost every concept its grounding
        and failed the whole plan."""
        brand, trend = cited(store)
        planner, _ = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[
                    draft(
                        brand_citations=[f"[{brand}]"],
                        trend_citations=[f"[{trend}]"],
                    )
                ],
            )
        )

        concept = planner.plan("serum campaign").concepts[0]

        assert brand in concept.brand_rationale
        assert trend in concept.trend_rationale

    def test_a_plan_with_no_concepts_fails(self, store, agent):
        planner, _ = agent(CampaignPlan(strategy_summary="s", concepts=[]))
        with pytest.raises(PlanningError, match="no concepts"):
            planner.plan("serum campaign")


class TestRetrievalStaysSeparate:
    def test_trend_chunks_are_never_offered_as_brand_citations(self, store, agent):
        brand, trend = cited(store)
        planner, _ = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[draft(brand_citations=[brand, trend], trend_citations=[trend])],
            )
        )

        concept = planner.plan("serum campaign").concepts[0]

        assert trend not in concept.brand_rationale


class TestBundledCorpora:
    def test_planning_runs_against_the_shipped_knowledge_base(self, tmp_path, agent):
        store = KnowledgeStore(path=tmp_path / "kb", embedder=local_embedder)
        # The packaged directories, not "data/…" relative to the shell — this
        # test otherwise only passes when pytest is run from `backend/`.
        ingest_directory(store, COMPANY_KB_DIR, corpus=COMPANY_KB)
        ingest_directory(store, TRENDS_DIR, corpus=TREND_CORPUS)

        brief = "Merdeka serum push"
        brand = store.retrieve_company(brief, k=1)[0].chunk_id
        trend = store.retrieve_trends(brief, k=1)[0].chunk_id
        provider = FakeProvider(
            CampaignPlan(
                strategy_summary="s",
                concepts=[draft(brand_citations=[brand], trend_citations=[trend])],
            )
        )

        plan = PlanningAgent(provider=provider, store=store).plan(brief)

        assert plan.concepts[0].brand_rationale


class TestRevisingAtTheGate:
    def test_the_humans_note_is_a_directive_in_the_prompt(self, store, agent):
        brand, trend = cited(store)
        planner, provider = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[draft(brand_citations=[brand], trend_citations=[trend])],
            )
        )
        original = planner.plan("serum campaign").concepts[0]

        planner.revise("serum campaign", original, "Make it about night routines.")

        prompt = provider.calls[1]["prompt"]
        assert "Make it about night routines." in prompt
        assert "REVISION REQUEST" in prompt

    def test_the_concept_being_edited_is_shown_to_the_planner(self, store, agent):
        brand, trend = cited(store)
        planner, provider = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[draft(brand_citations=[brand], trend_citations=[trend])],
            )
        )
        original = planner.plan("serum campaign").concepts[0]

        planner.revise("serum campaign", original, "Softer tone.")

        assert "Reapplication, humidity edition" in provider.calls[1]["prompt"]

    def test_a_revision_keeps_the_concepts_identity(self, store, agent):
        brand, trend = cited(store)
        planner, _ = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[draft(brand_citations=[brand], trend_citations=[trend])],
            )
        )
        original = planner.plan("serum campaign").concepts[0]

        revised = planner.revise("serum campaign", original, "Softer tone.")

        assert revised.concept_id == original.concept_id
        assert revised.status is ConceptStatus.EDITED

    def test_a_revision_is_still_held_to_its_grounding(self, store, agent):
        _, trend = cited(store)
        planner, _ = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[
                    draft(
                        theme="Ungrounded rework",
                        brand_citations=["brand.md#99-deadbeef"],
                        trend_citations=[trend],
                    )
                ],
            )
        )
        original = Concept(
            concept_id="c-1",
            theme="Original",
            format="image",
            trend_rationale="t",
            brand_rationale="b",
            variant_count=1,
            variation_axes=["hook"],
        )

        with pytest.raises(PlanningError, match="Ungrounded rework"):
            planner.revise("serum campaign", original, "Promise whitening.")

    def test_an_empty_note_is_refused(self, store, agent):
        brand, trend = cited(store)
        planner, _ = agent(
            CampaignPlan(
                strategy_summary="s",
                concepts=[draft(brand_citations=[brand], trend_citations=[trend])],
            )
        )
        original = planner.plan("serum campaign").concepts[0]

        with pytest.raises(ValueError, match="revision note"):
            planner.revise("serum campaign", original, "   ")
