"""The automated QA pass that runs before a human sees a creative.

The plan puts this ahead of the review gate on purpose (`plan:43`): a reviewer's
attention is the scarcest thing in the pipeline, and spending it on an asset with
a warped hand in it is waste. QA is the machine's own first look.

It never blocks. A provider that cannot accept an image, or a model that returns
something unusable, degrades to `flagged` with a note saying so — a degraded QA
pass costs a human a look, a broken one costs the demo.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from app.agents.base import Provider, with_house_note
from app.domain import VisualBrief

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the quality checker for a Malaysian SME's marketing \
team. You are shown one finished ad creative and you decide whether a human \
should be asked to look at it.

The headline and call to action were composited onto the image after it was \
generated, so they are crisp by construction. What you are judging is whether \
they are *readable where they landed* and whether the picture underneath them \
holds up.

Flag the asset if any of these are true:
- The headline or call to action is hard to read against what sits behind it.
- The text covers the subject's face or the focal point of the image.
- The image has obvious generation artifacts — malformed hands, extra limbs, \
nonsense objects, warped faces.
- Anything in the frame contradicts the brand or would embarrass the advertiser.
- There is garbled text *in the picture itself*, separate from the composited words.

Pass it otherwise. Passing is the normal outcome; do not invent problems.

When you flag, `notes` says what is wrong in one sentence, specific enough that \
the image can be re-prompted from it. When you pass, `notes` is empty."""


class QAVerdict(BaseModel):
    """The structured output contract the provider is held to."""

    status: Literal["passed", "flagged"]
    notes: str = ""


class VisionQA:
    def __init__(self, *, provider: Provider, standing_note: str | None = None) -> None:
        self.provider = provider
        self.system = with_house_note(SYSTEM_PROMPT, standing_note)

    def review(
        self,
        image: bytes,
        *,
        headline: str,
        cta: str,
        brief: VisualBrief,
    ) -> QAVerdict:
        try:
            return self.provider.structured(
                system=self.system,
                prompt=self.build_prompt(headline=headline, cta=cta, brief=brief),
                schema=QAVerdict,
                images=[image],
            )
        except Exception as error:
            # Degrade, never block. The human still gets the asset — they just
            # get it without the machine's opinion attached.
            log.warning("vision QA could not review an asset: %s", error)
            return QAVerdict(
                status="flagged",
                notes=(
                    "This asset could not be checked automatically "
                    f"({error}). Please review it yourself."
                ),
            )

    # -- prompt ------------------------------------------------------------

    def build_prompt(self, *, headline: str, cta: str, brief: VisualBrief) -> str:
        return "\n".join(
            [
                "## WHAT WAS COMPOSITED ONTO THIS IMAGE",
                f"Headline: {headline}",
                f"Call to action: {cta}",
                f"Placed at: {brief.placement_zone}",
                "",
                "## WHAT THE IMAGE WAS SUPPOSED TO BE",
                brief.image_prompt,
                "",
                "## HOW IT WAS SUPPOSED TO BE LAID OUT",
                brief.composition_notes,
                "",
                "Judge the attached image against the above.",
            ]
        )
