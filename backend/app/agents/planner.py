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
from typing import Protocol

from pydantic import BaseModel, Field

from app.domain import Concept, ConceptFormat
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


class Provider(Protocol):
    """Whatever LLM the campaign is running on — see `app.llm`."""

    def structured(self, *, system: str, prompt: str, schema: type[BaseModel]): ...


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
    def __init__(self, *, provider: Provider, store: KnowledgeStore) -> None:
        self.provider = provider
        self.store = store

    def plan(
        self,
        brief: str,
        *,
        source_event: str | None = None,
        concept_count: int = DEFAULT_CONCEPT_COUNT,
    ) -> PlanResult:
        brief = brief.strip()
        if not brief:
            raise ValueError("a campaign brief is required")

        # Two retrievals, never one: the corpora stay separable all the way
        # through the prompt so a citation's provenance is unambiguous.
        company_context = self.store.retrieve_company(brief, k=COMPANY_K)
        trend_context = self.store.retrieve_trends(brief, k=TREND_K)

        plan = self.provider.structured(
            system=SYSTEM_PROMPT,
            prompt=self.build_prompt(
                brief,
                company_context=company_context,
                trend_context=trend_context,
                source_event=source_event,
                concept_count=concept_count,
            ),
            schema=CampaignPlan,
        )

        return PlanResult(
            strategy_summary=plan.strategy_summary,
            concepts=self._to_concepts(
                plan, company_context, trend_context, source_event
            ),
            company_context=company_context,
            trend_context=trend_context,
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
            self._render(company_context, empty="No company knowledge retrieved."),
            "",
            "## TREND SIGNALS (inspiration only — cite these as trend_citations)",
            self._render(trend_context, empty="No trend signals retrieved."),
            "",
            f"Produce exactly {concept_count} distinct concepts.",
        ]
        return "\n".join(sections)

    @staticmethod
    def _render(context: list[Retrieved], *, empty: str) -> str:
        if not context:
            return empty
        return "\n\n".join(
            f"[{hit.chunk_id}] ({hit.source} § {hit.heading})\n{hit.text}"
            for hit in context
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
