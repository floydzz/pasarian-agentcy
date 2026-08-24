"""The copywriter agent: one approved concept in, one copy variant per axis out.

The concept's `variation_axes` are the whole point of this agent. They are the
diversity strategy the planner committed to, and this agent has to actually
execute it — one variant per axis, each different because of the axis it names,
not because a synonym got swapped in.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.agents.base import CrewError, Provider, render_context, with_house_note
from app.domain import Concept
from app.rag.store import Retrieved

SYSTEM_PROMPT = """You are the copywriter for a Malaysian SME's marketing team. \
You turn one approved campaign concept into a set of genuinely different ad copy \
variants.

COMPANY KNOWLEDGE is ground truth. Brand voice, product facts and claim \
guardrails come only from there. Never invent a product fact it does not state, \
and never make a claim its guardrails forbid.

You are given the concept's variation axes. Each axis is one creative lever, and \
you write exactly one variant per axis, in the order the axes are given:

- The named axis must be what makes the variant different. If the axis is "cta \
phrasing", the call to action is what changes. If it is "emotional hook", the \
opening beat is what changes.
- Set `hook_type` to the axis that variant executes, copied exactly as given.
- Variants must be really different, not one line reworded. If two variants \
could stand in for each other, they have failed.
- Headlines are short enough to sit legibly on an image. Body copy is two \
sentences at most. Every variant lands on a concrete call to action.
- Write in the brand's voice as the company knowledge describes it, including \
its language mix."""


class CopyDraft(BaseModel):
    """One variant's copy, before the visual planner has seen it."""

    hook_type: str
    headline: str
    body: str
    cta: str


class CopySet(BaseModel):
    """The structured output contract the provider is held to."""

    variants: list[CopyDraft]


class Copywriter:
    def __init__(self, *, provider: Provider, standing_note: str | None = None) -> None:
        self.provider = provider
        self.system = with_house_note(SYSTEM_PROMPT, standing_note)

    def write(
        self,
        concept: Concept,
        *,
        brand_context: list[Retrieved],
        revision_notes: str | None = None,
    ) -> list[CopyDraft]:
        drafted = self.provider.structured(
            system=self.system,
            prompt=self.build_prompt(
                concept, brand_context=brand_context, revision_notes=revision_notes
            ),
            schema=CopySet,
        )
        return self._align(drafted.variants, concept)

    # -- prompt ------------------------------------------------------------

    def build_prompt(
        self,
        concept: Concept,
        *,
        brand_context: list[Retrieved],
        revision_notes: str | None,
    ) -> str:
        axes = "\n".join(
            f"{position}. {axis}"
            for position, axis in enumerate(concept.variation_axes, start=1)
        )
        sections = [
            "## CONCEPT (approved — this is what you are writing)",
            f"Theme: {concept.theme}",
            f"Format: {concept.format}",
            f"Why it fits the brand: {concept.brand_rationale}",
            f"Why it fits the moment: {concept.trend_rationale}",
            "",
            "## VARIATION AXES (one variant each, in this order)",
            axes,
            "",
            "## COMPANY KNOWLEDGE (ground truth)",
            render_context(brand_context, empty="No company knowledge retrieved."),
        ]
        if revision_notes:
            sections += [
                "",
                "## DIRECTOR'S NOTES (a previous pass was sent back — fix these)",
                revision_notes,
            ]
        sections += ["", f"Write exactly {concept.variant_count} variants."]
        return "\n".join(sections)

    # -- verification ------------------------------------------------------

    @staticmethod
    def _align(drafts: list[CopyDraft], concept: Concept) -> list[CopyDraft]:
        """Hold the model to one variant per axis.

        A wrong count breaks the concept's diversity promise outright, so it
        fails. A mislabelled `hook_type` does not — the variants come back in
        axis order, so an unrecognised label is snapped to the axis at that
        position rather than being carried through as a phantom axis.
        """
        if len(drafts) != concept.variant_count:
            raise CrewError(
                f"copywriter returned {len(drafts)} variants for concept "
                f"{concept.theme!r}, which needs exactly {concept.variant_count} "
                "— one per variation axis"
            )

        by_label = {axis.strip().lower(): axis for axis in concept.variation_axes}
        return [
            draft.model_copy(
                update={
                    "hook_type": by_label.get(
                        draft.hook_type.strip().lower(),
                        concept.variation_axes[position],
                    )
                }
            )
            for position, draft in enumerate(drafts)
        ]
