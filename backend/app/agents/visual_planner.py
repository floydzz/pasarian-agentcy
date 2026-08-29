"""The visual planner agent: finished copy in, a shootable image brief out.

This agent runs *after* the copywriter and is given the real headline, body and
CTA — not the concept's theme. Planning composition and text placement without
the actual words is how you get a layout with nowhere for the headline to go, so
the copy is fixed input here and the agent is told it may not rewrite it.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.agents.base import CrewError, Provider, render_context, with_house_note
from app.agents.copywriter import CopyDraft
from app.domain import Concept, PlacementZone, TextTreatment
from app.rag.store import Retrieved

SYSTEM_PROMPT = """You are the visual planner for a Malaysian SME's marketing \
team. You are handed ad copy that is already written and final, and you plan the \
image each variant needs.

The copy is fixed. Plan around it. Never rewrite it and never ask for it to \
change.

For every variant, in the order given:

- `image_prompt` is what an image generation model receives. Describe subject, \
setting, lighting, composition and mood concretely. Never ask it to render text: \
the headline and call to action are composited on afterwards. One paragraph.
- `text_placement` says where the actual headline and call to action sit in the \
frame, naming the real words being placed.
- `placement_zone` is that same decision as one of: top-left, top-center, \
top-right, mid-left, mid-center, mid-right, bottom-left, bottom-center, \
bottom-right. It must agree with `text_placement`. The headline is composited \
onto the image afterwards at exactly this zone, so `image_prompt` must ask for \
clear, uncluttered space there — never put a face or the subject's focal point \
in the zone you chose.
- `text_treatment` chooses how the exact headline and CTA are protected after \
generation. It must be one of: `bare` (no panel; subtle text outline only), \
`soft-gradient` (a diffuse, borderless contrast gradient), `glass-panel` (a \
tight translucent rounded panel), or `ribbon` (a slim editorial band). Choose \
what fits the specific scene and the density behind the words. Across a set of \
two or more variants, use at least two treatments whenever doing so preserves \
legibility; do not give every concept the same default box.
- `composition_notes` explain the layout to a human reviewer: where the eye \
lands first, what negative space the text sits in, and why this text treatment \
fits the composition.

COMPANY KNOWLEDGE is ground truth for how the brand is allowed to look — \
respect it over any instinct of your own.

Each variant executes a different creative axis, so the images must differ too. \
Re-shooting one setup with a new caption pasted on is a failure.

Return one JSON object whose only top-level collection is `briefs`. Each item
in `briefs` is one VisualDraft in the supplied copy order. Do not call that
collection `variants`: that is the copywriter's contract, not yours."""


class VisualDraft(BaseModel):
    """One variant's image brief — mirrors `domain.VisualBrief`."""

    composition_notes: str
    image_prompt: str
    text_placement: str
    placement_zone: PlacementZone
    text_treatment: TextTreatment


class VisualSet(BaseModel):
    """The structured output contract the provider is held to."""

    briefs: list[VisualDraft]


class VisualPlanner:
    def __init__(self, *, provider: Provider, standing_note: str | None = None) -> None:
        self.provider = provider
        self.system = with_house_note(SYSTEM_PROMPT, standing_note)

    def plan(
        self,
        concept: Concept,
        copy: list[CopyDraft],
        *,
        brand_context: list[Retrieved],
        revision_notes: str | None = None,
    ) -> list[VisualDraft]:
        drafted = self.provider.structured(
            system=self.system,
            prompt=self.build_prompt(
                concept,
                copy,
                brand_context=brand_context,
                revision_notes=revision_notes,
            ),
            schema=VisualSet,
        )

        if len(drafted.briefs) != len(copy):
            raise CrewError(
                f"visual planner returned {len(drafted.briefs)} briefs for "
                f"{len(copy)} copy variants — every variant needs exactly one"
            )
        return drafted.briefs

    # -- prompt ------------------------------------------------------------

    def build_prompt(
        self,
        concept: Concept,
        copy: list[CopyDraft],
        *,
        brand_context: list[Retrieved],
        revision_notes: str | None,
    ) -> str:
        written = "\n\n".join(
            "\n".join(
                [
                    f"### Variant {position} — axis: {draft.hook_type}",
                    f"Headline: {draft.headline}",
                    f"Body: {draft.body}",
                    f"CTA: {draft.cta}",
                ]
            )
            for position, draft in enumerate(copy, start=1)
        )
        sections = [
            "## CONCEPT",
            f"Theme: {concept.theme}",
            f"Format: {concept.format}",
            "",
            "## FINAL COPY (fixed — plan around these exact words)",
            written,
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
        sections += [
            "",
            f"Produce exactly {len(copy)} briefs, one per variant, in order.",
        ]
        return "\n".join(sections)
