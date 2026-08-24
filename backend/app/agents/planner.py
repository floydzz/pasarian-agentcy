"""The planning agent: brief in, grounded campaign concepts out.

Three inputs feed the prompt and they are not equal. The human brief is a
directive. The company knowledge base is ground truth — it can veto an idea. The
trend corpus is inspiration only — it can suggest an angle and never a fact. The
prompt states that ranking explicitly, and every concept must cite the chunks it
leaned on so a human at the approval gate can check the work.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.agents.base import Provider, render_context, with_house_note
from app.agents.events import AgentEvent, EventSink, emit
from app.domain import Concept, ConceptFormat, ConceptStatus
from app.rag.store import KnowledgeStore, Retrieved

DEFAULT_CONCEPT_COUNT = 3
COMPANY_K = 6
TREND_K = 6

SYSTEM_PROMPT = """You are the planning strategist for a Malaysian SME's \
marketing team. You turn a campaign brief into distinct, grounded creative \
concepts.

Your three sources are not equal:

1. THE BRIEF is a directive. It sets the goal, the product, and the occasion.
2. COMPANY KNOWLEDGE is ground truth. Brand voice, guardrails, product facts \
and past campaign learnings come only from here. It can veto an idea outright. \
Never contradict it, never invent a product fact it does not state.
3. TREND SIGNALS are inspiration only, never fact. A trend can suggest an \
angle; it can never justify a claim about the product or the brand. If a trend \
conflicts with company knowledge, company knowledge wins and you drop the trend.

Rules for every concept you produce:

- Cite the chunk ids you actually used, in `brand_citations` and \
`trend_citations`. Use ids exactly as given. Never cite an id you were not \
shown, and never cite a trend chunk as brand grounding.
- Ground every concept in at least one company knowledge chunk.
- `variation_axes` names what changes between the variants of this concept — \
one axis per variant, so `len(variation_axes)` must equal `variant_count`. \
Axes are concrete creative levers (hook, setting, cast, proof, CTA, format), \
not restatements of the theme.
- Concepts must be genuinely distinct from one another, not one idea reworded.
- Respect every guardrail in the company knowledge, especially claim \
restrictions. A concept that needs a forbidden claim is not a concept."""


class PlanningError(RuntimeError):
    """The model returned a plan that cannot be trusted or used."""


class ConceptDraft(BaseModel):
    """One concept as the model produces it — no ids, no status yet."""

    theme: str
    format: ConceptFormat
    trend_rationale: str
    brand_rationale: str
    variant_count: int = Field(ge=1, le=6)
    variation_axes: list[str] = Field(min_length=1, max_length=6)
    brand_citations: list[str] = Field(
        default_factory=list, description="chunk ids from COMPANY KNOWLEDGE"
    )
    trend_citations: list[str] = Field(
        default_factory=list, description="chunk ids from TREND SIGNALS"
    )


class CampaignPlan(BaseModel):
    """The structured output contract the provider is held to."""

    strategy_summary: str
    concepts: list[ConceptDraft]


@dataclass
class PlanResult:
    strategy_summary: str
    concepts: list[Concept]
    company_context: list[Retrieved]
    trend_context: list[Retrieved]


class PlanningAgent:
    def __init__(
        self,
        *,
        provider: Provider,
        store: KnowledgeStore,
        standing_note: str | None = None,
        concept_count: int = DEFAULT_CONCEPT_COUNT,
        company_k: int = COMPANY_K,
        trend_k: int = TREND_K,
    ) -> None:
        self.provider = provider
        self.store = store
        self.system = with_house_note(SYSTEM_PROMPT, standing_note)
        self.concept_count = concept_count
        self.company_k = company_k
        self.trend_k = trend_k

    def plan(
        self,
        brief: str,
        *,
        source_event: str | None = None,
        concept_count: int | None = None,
        sink: EventSink | None = None,
    ) -> PlanResult:
        brief = brief.strip()
        if not brief:
            raise ValueError("a campaign brief is required")
        if concept_count is None:
            concept_count = self.concept_count

        emit(sink, AgentEvent("planner", "started", "Reading the brief"))

        # Two retrievals, never one: the corpora stay separable all the way
        # through the prompt so a citation's provenance is unambiguous.
        company_context = self.store.retrieve_company(brief, k=self.company_k)
        trend_context = self.store.retrieve_trends(brief, k=self.trend_k)
        emit(
            sink,
            AgentEvent(
                "planner",
                "started",
                f"Retrieved {len(company_context)} brand chunks and "
                f"{len(trend_context)} trend chunks, kept separate",
                {
                    "brand": [hit.chunk_id for hit in company_context],
                    "trend": [hit.chunk_id for hit in trend_context],
                },
            ),
        )

        emit(
            sink,
            AgentEvent("planner", "started", f"Proposing {concept_count} concepts"),
        )
        plan = self.provider.structured(
            system=self.system,
            prompt=self.build_prompt(
                brief,
                company_context=company_context,
                trend_context=trend_context,
                source_event=source_event,
                concept_count=concept_count,
            ),
            schema=CampaignPlan,
        )

        emit(
            sink,
            AgentEvent(
                "planner",
                "started",
                f"Verifying citations on {len(plan.concepts)} concepts",
            ),
        )
        result = PlanResult(
            strategy_summary=plan.strategy_summary,
            concepts=self._to_concepts(
                plan, company_context, trend_context, source_event
            ),
            company_context=company_context,
            trend_context=trend_context,
        )
        emit(
            sink,
            AgentEvent(
                "planner",
                "finished",
                f"{len(result.concepts)} grounded concepts ready for review",
                {"themes": [concept.theme for concept in result.concepts]},
            ),
        )
        return result

    def revise(self, brief: str, concept: Concept, note: str) -> Concept:
        """Rework one concept around a human's note from the approval gate.

        This is the "edit" branch of the gate. The human's note is a directive
        alongside the brief, but it does not escape the grounding rules — the
        revision is retrieved and cited exactly like a fresh concept, so a
        reviewer cannot talk the planner into an ungrounded idea by asking
        nicely.
        """
        note = note.strip()
        if not note:
            raise ValueError("a revision note is required")

        query = f"{brief}\n{note}"
        company_context = self.store.retrieve_company(query, k=self.company_k)
        trend_context = self.store.retrieve_trends(query, k=self.trend_k)

        plan = self.provider.structured(
            system=self.system,
            prompt=self.build_revision_prompt(
                brief,
                concept,
                note,
                company_context=company_context,
                trend_context=trend_context,
            ),
            schema=CampaignPlan,
        )

        revised = self._to_concepts(
            plan, company_context, trend_context, concept.provenance
        )
        # The concept keeps its identity: the human edited this idea, they did
        # not ask for an extra one beside it.
        return revised[0].model_copy(
            update={
                "concept_id": concept.concept_id,
                "status": ConceptStatus.EDITED,
            }
        )

    # -- prompt ------------------------------------------------------------

    def build_prompt(
        self,
        brief: str,
        *,
        company_context: list[Retrieved],
        trend_context: list[Retrieved],
        source_event: str | None,
        concept_count: int,
    ) -> str:
        sections = [
            "## BRIEF (directive)",
            brief,
        ]
        if source_event:
            sections += ["", f"Occasion driving this campaign: {source_event}"]
        sections += [
            "",
            "## COMPANY KNOWLEDGE (ground truth — cite these as brand_citations)",
            render_context(company_context, empty="No company knowledge retrieved."),
            "",
            "## TREND SIGNALS (inspiration only — cite these as trend_citations)",
            render_context(trend_context, empty="No trend signals retrieved."),
            "",
            f"Produce exactly {concept_count} distinct concepts.",
        ]
        return "\n".join(sections)

    def build_revision_prompt(
        self,
        brief: str,
        concept: Concept,
        note: str,
        *,
        company_context: list[Retrieved],
        trend_context: list[Retrieved],
    ) -> str:
        return "\n".join(
            [
                "## BRIEF (directive)",
                brief,
                "",
                "## CONCEPT AS IT STANDS",
                f"Theme: {concept.theme}",
                f"Format: {concept.format}",
                f"Trend rationale: {concept.trend_rationale}",
                f"Brand rationale: {concept.brand_rationale}",
                f"Variation axes: {', '.join(concept.variation_axes)}",
                "",
                "## REVISION REQUEST (directive — a human reviewed the concept "
                "above and asked for this change)",
                note,
                "",
                "## COMPANY KNOWLEDGE (ground truth — cite these as brand_citations)",
                render_context(company_context, empty="No company knowledge retrieved."),
                "",
                "## TREND SIGNALS (inspiration only — cite these as trend_citations)",
                render_context(trend_context, empty="No trend signals retrieved."),
                "",
                "Produce exactly 1 concept: this one, reworked around the "
                "revision request. Keep what the human did not ask you to "
                "change. The revision request does not loosen the grounding "
                "rules — if it asks for something company knowledge forbids, "
                "get as close as the guardrails allow and say so in the brand "
                "rationale.",
            ]
        )

    # -- verification ------------------------------------------------------

    def _to_concepts(
        self,
        plan: CampaignPlan,
        company_context: list[Retrieved],
        trend_context: list[Retrieved],
        source_event: str | None,
    ) -> list[Concept]:
        if not plan.concepts:
            raise PlanningError("the planner returned no concepts")

        brand_ids = {hit.chunk_id for hit in company_context}
        trend_ids = {hit.chunk_id for hit in trend_context}

        concepts: list[Concept] = []
        for drafted in plan.concepts:
            # Citations are checked against what the model was actually shown —
            # an id it invented, or borrowed from the other corpus, is dropped.
            brand_citations = [c for c in drafted.brand_citations if c in brand_ids]
            trend_citations = [c for c in drafted.trend_citations if c in trend_ids]

            if not brand_citations:
                raise PlanningError(
                    f"concept {drafted.theme!r} cites no company knowledge — "
                    "it is not grounded in the brand"
                )

            concepts.append(
                Concept(
                    concept_id=str(uuid.uuid4()),
                    theme=drafted.theme,
                    format=drafted.format,
                    trend_rationale=_with_citations(
                        drafted.trend_rationale, trend_citations
                    ),
                    brand_rationale=_with_citations(
                        drafted.brand_rationale, brand_citations
                    ),
                    variant_count=drafted.variant_count,
                    variation_axes=drafted.variation_axes,
                    provenance=source_event,
                )
            )
        return concepts


def _with_citations(rationale: str, citations: list[str]) -> str:
    """Keep the citation inside the stored text so the reviewer sees it."""
    if not citations:
        return rationale
    return f"{rationale.rstrip()} [sources: {', '.join(citations)}]"
