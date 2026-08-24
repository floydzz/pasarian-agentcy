"""The director agent: the crew's quality gate before a human spends attention.

The director sees copy and visuals as pairs, because that is how they will be
judged. It answers one question with consequences: send this back to the
copywriter, send it back to the visual planner, or let it through. It is
deliberately not allowed to rewrite anything itself — a reviewer that edits its
own work stops being a reviewer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.agents.base import Provider, render_context, with_house_note
from app.agents.copywriter import CopyDraft
from app.agents.visual_planner import VisualDraft
from app.domain import Concept
from app.rag.store import Retrieved

#: Which agent a revision goes back to. "pass" ends the crew's work.
Verdict = Literal["pass", "revise_copy", "revise_visuals"]

#: Stand-in when the model asks for a revision but says nothing useful. The
#: downstream agent still needs *something* to act on, and a human reading a
#: flagged variant deserves to know the review itself was thin.
UNEXPLAINED = (
    "The director asked for a revision without giving a reason. Re-examine the "
    "variants for brand-voice drift and for two variants that say the same thing."
)

SYSTEM_PROMPT = """You are the creative director for a Malaysian SME's marketing \
team. A copywriter and a visual planner have produced a set of ad variants and \
you decide whether they ship.

Judge each copy and image brief as a pair, the way an audience will see them, \
against three tests:

1. BRAND. Does the copy sound like the brand as COMPANY KNOWLEDGE describes it? \
Does anything make a claim the guardrails forbid, or state a product fact the \
company knowledge does not support? This test can fail a set on its own.
2. DIVERSITY. Each variant was assigned a variation axis. Do the variants \
actually differ along those axes, or is this one idea reworded three times? \
Judge the real difference between them, not whether they use different words. \
Two variants that could stand in for each other is a failure.
3. EXECUTION. Does each image brief fit its copy — is there room in the frame \
for the real headline and CTA, and does the brief describe an image a generator \
could actually produce?

Then return one verdict:

- `pass` — the set is ready for a human.
- `revise_copy` — the problem is in the writing: voice, claims, or two variants \
that are not really different. The copywriter will rewrite, and the visuals \
will be replanned around the new copy.
- `revise_visuals` — the copy is fine and the problem is only in the image \
briefs.

If the copy needs work, choose `revise_copy` even if the visuals are also weak — \
replanned copy needs replanned visuals anyway.

Whenever you do not pass the set, `notes` must say specifically what is wrong \
and what to change. The agent receiving it sees your notes and nothing else, so \
vague notes waste a revision pass. Name the variant and the fix."""


class DirectorVerdict(BaseModel):
    """The structured output contract the provider is held to."""

    verdict: Verdict
    notes: str = Field(
        default="",
        description="Required unless the verdict is pass — what to fix, and where",
    )


class Director:
    def __init__(self, *, provider: Provider, standing_note: str | None = None) -> None:
        self.provider = provider
        self.system = with_house_note(SYSTEM_PROMPT, standing_note)

    def review(
        self,
        concept: Concept,
        copy: list[CopyDraft],
        visuals: list[VisualDraft],
        *,
        brand_context: list[Retrieved],
    ) -> DirectorVerdict:
        verdict = self.provider.structured(
            system=self.system,
            prompt=self.build_prompt(
                concept, copy, visuals, brand_context=brand_context
            ),
            schema=DirectorVerdict,
        )

        if verdict.verdict == "pass":
            # A passing verdict carries no notes — nothing is being sent back.
            return verdict.model_copy(update={"notes": ""})
        if not verdict.notes.strip():
            return verdict.model_copy(update={"notes": UNEXPLAINED})
        return verdict

    # -- prompt ------------------------------------------------------------

    def build_prompt(
        self,
        concept: Concept,
        copy: list[CopyDraft],
        visuals: list[VisualDraft],
        *,
        brand_context: list[Retrieved],
    ) -> str:
        pairs = "\n\n".join(
            "\n".join(
                [
                    f"### Variant {position} — assigned axis: {written.hook_type}",
                    f"Headline: {written.headline}",
                    f"Body: {written.body}",
                    f"CTA: {written.cta}",
                    f"Composition: {planned.composition_notes}",
                    f"Image prompt: {planned.image_prompt}",
                    f"Text placement: {planned.text_placement}",
                ]
            )
            for position, (written, planned) in enumerate(
                zip(copy, visuals, strict=True), start=1
            )
        )
        return "\n".join(
            [
                "## CONCEPT",
                f"Theme: {concept.theme}",
                f"Format: {concept.format}",
                f"Promised variation axes: {', '.join(concept.variation_axes)}",
                "",
                "## VARIANTS UNDER REVIEW",
                pairs,
                "",
                "## COMPANY KNOWLEDGE (ground truth)",
                render_context(brand_context, empty="No company knowledge retrieved."),
            ]
        )
