"""An offline provider for rehearsing the pipeline. Not a model.

The risk register says not to depend on a live API during the demo, and a
console that can only be shown with a funded key is a console that cannot be
rehearsed. This provider fills the same `structured()` contract with canned
output built from whatever chunks the prompt actually carried, so the grounding
checks, the citation verification and the director's revision loop all run for
real — only the writing is fake.

Select it with `LLM_PROVIDER=demo`. It produces obviously-placeholder copy on
purpose: nothing it returns should ever be mistaken for the model's work.
"""

from __future__ import annotations

import re
import time
from typing import Any

from .base import LLMProvider, T

#: Chunk ids as `render_context` writes them into a prompt: `[brand.md#0-ab12]`.
CHUNK = re.compile(r"\[([^\]\s]+#[^\]\s]+)\]")

#: How long each "call" takes. Long enough that the console's breathing states
#: and edge pulses are visible while rehearsing, short enough to sit through.
LATENCY_SECONDS = 1.2


class DemoProvider(LLMProvider):
    """Canned structured output, shaped by the prompt it was given."""

    def __init__(self, *, api_key: str = "demo", model: str | None = None,
                 max_tokens: int = 4096, reasoning: bool = False,
                 fallback_models: list[str] | None = None) -> None:
        # Deliberately not calling super(): this provider has no key to demand.
        self.api_key = api_key
        self.model = model or self.default_model
        self.max_tokens = max_tokens
        # Accepted and ignored. There is no model here to deliberate, but a
        # rehearsal that refused a keyword the live providers take would fail
        # only when someone switched to it — which is the worst time to find out.
        self.reasoning = reasoning
        # Accepted and ignored for the same reason as `reasoning`: there is no
        # quota here to run out of.
        self.fallback_models = list(fallback_models or [])
        self._reviews = 0

    @property
    def default_model(self) -> str:
        return "demo-offline"

    def build_request(self, *, system: str, prompt: str, schema: type[T],
                      images: list[bytes] | None = None) -> dict[str, Any]:
        return {"model": self.model, "system": system, "prompt": prompt,
                "schema": schema.__name__, "images": len(images or [])}

    def structured(self, *, system: str, prompt: str, schema: type[T],
                   images: list[bytes] | None = None) -> T:
        time.sleep(LATENCY_SECONDS)

        name = schema.__name__
        if name == "CampaignPlan":
            return schema(**self._plan(prompt))
        if name == "CopySet":
            return schema(**self._copy(prompt))
        if name == "VisualSet":
            return schema(**self._visuals(prompt))
        if name == "DirectorVerdict":
            return schema(**self._verdict())
        if name == "QAVerdict":
            return schema(**self._qa())
        if name == "ChatTurn":
            return schema(**self._chat(prompt))
        raise ValueError(f"the demo provider has no canned answer for {name}")

    # -- canned answers ----------------------------------------------------

    def _plan(self, prompt: str) -> dict:
        brand, trend = self._citations(prompt)
        wanted = self._int_after(prompt, r"exactly (\d+) distinct concepts", default=3)
        revising = "REVISION REQUEST" in prompt
        if revising:
            wanted = 1

        axes = [
            ["emotional hook", "proof shown", "cta phrasing"],
            ["value framing", "cta phrasing"],
            ["everyday moment", "before and after", "cta phrasing"],
        ]
        themes = [
            "[demo] The problem your customer already feels",
            "[demo] The bundle, priced for the moment",
            "[demo] One honest before and after",
        ]
        if revising:
            themes = ["[demo] Reworked around your note"]

        return {
            "strategy_summary": (
                "[demo] Offline rehearsal plan — lead with the problem, keep every "
                "claim inside the brand guardrails."
            ),
            "concepts": [
                {
                    "theme": themes[index % len(themes)],
                    "format": ["image", "carousel", "video"][index % 3],
                    "trend_rationale": "[demo] Matches what is running well right now.",
                    "brand_rationale": "[demo] Sits inside the brand's stated position.",
                    "variant_count": len(axes[index % len(axes)]),
                    "variation_axes": axes[index % len(axes)],
                    "brand_citations": brand[:2],
                    "trend_citations": trend[:2],
                }
                for index in range(wanted)
            ],
        }

    def _chat(self, prompt: str) -> dict:
        """A usable rehearsal of the strategist's small action vocabulary.

        This is intentionally simple, not an attempt to imitate reasoning. It
        recognises the pipeline state the real prompt supplies so an offline
        walkthrough can still create a thread, run a plan, wait at the gate,
        and start generation after a person approves concepts.
        """
        message = prompt.split("## NEW MESSAGE", 1)[-1].strip()
        lower = message.lower()
        affirmative = any(
            phrase in lower
            for phrase in ("plan", "go ahead", "start", "let's do", "lets do", "proceed", "generate", "continue", "next")
        )
        variants = self._int_after(prompt, r"Variants: (\d+)", default=0)
        assets = self._int_after(prompt, r"Assets: (\d+)", default=0)
        videos = self._int_after(prompt, r"Videos: (\d+)", default=0)
        pending_videos = self._int_after(prompt, r"Pending videos: (\d+)", default=0)
        approved_videos = self._int_after(prompt, r"Approved videos: (\d+)", default=0)

        if ("cinematic" in lower or "trailer" in lower) and (
            "demo" in lower or "cut" in lower
        ):
            return {
                "reply": "[scripted demo] Opening the seeded cinematic cut. It is a completed local production asset with its shot breakdown, so no video generation or tokens are used.",
                "action": "open_cinematic_demo",
            }

        if "No campaign is attached" in prompt:
            if len(message) < 28:
                return {
                    "reply": "[demo] Tell me what you are promoting, who it is for, and the outcome you want. I will turn that into a campaign brief.",
                    "action": "none",
                }
            title_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’/-]*", message)[:6]
            title = "[demo] " + (" ".join(title_words) or "Marketing campaign")
            return {
                "reply": "[scripted demo] Campaign brief created with no model call. Reply “Plan this campaign” and I will open the live Image Studio planning console.",
                "action": "create_campaign",
                "draft": {"name": title[:200], "brief": f"[scripted demo] {message}"},
            }

        if "Status: draft" in prompt and affirmative:
            return {
                "reply": "[scripted demo] Starting the saved offline planning script. It uses zero model tokens and will stop at the concept approval gate.",
                "action": "run_plan",
            }
        if "Status: generating" in prompt and variants == 0 and affirmative:
            return {
                "reply": "[scripted demo] Starting the offline creative crew for the approved concepts. Reply “Continue image generation” again when the copy variants are ready, and I will render from your saved media library.",
                "action": "run_generate",
            }
        if "Status: generating" in prompt and variants > 0 and assets == 0:
            return {
                "reply": "[scripted demo] The copy variants are ready. I am opening Image Studio to reuse your existing generated assets, run the scripted QA events, and create new campaign-owned copies instantly.",
                "action": "run_render",
            }
        if "Status: pending_plan_approval" in prompt:
            return {
                "reply": "[scripted demo] The concepts are ready. I am opening Image Studio—approve at least one concept, close the plan gate, then ask me to “Continue image generation”.",
                "action": "open_image",
            }
        if "Status: pending_asset_review" in prompt:
            return {
                "reply": "[scripted demo] The reused image creatives are waiting at the real review gate. Approve the ones you want, close the gate, then ask me to “Generate the campaign video”.",
                "action": "open_image",
            }
        if "Status: ready_to_publish" in prompt:
            if approved_videos > 0 or "publish" in lower:
                return {
                    "reply": "[scripted demo] The approved image and video ads are ready. I am opening Publish for channel previews, copy, and downloads. Nothing will be posted to a live account.",
                    "action": "open_publish",
                }
            if pending_videos > 0:
                return {
                    "reply": "[scripted demo] The campaign video is already rendered. I am opening Video Studio so you can approve the cut, then ask me to “Open Publish”.",
                    "action": "open_video",
                }
            if videos == 0:
                return {
                    "reply": "[scripted demo] I am opening Video Studio and rendering a campaign cut from the saved storyboard and existing local video. No video model or tokens are used.",
                    "action": "run_video",
                }
        return {
            "reply": "[scripted demo] I have the current campaign state. Reply “Continue image generation”, “Generate the campaign video”, or “Open Publish”; I will choose the safe next stage without crossing a review gate.",
            "action": "none",
        }

    def _copy(self, prompt: str) -> dict:
        axes = re.findall(r"^\d+\.\s+(.+)$", prompt, flags=re.MULTILINE)
        count = self._int_after(prompt, r"exactly (\d+) variants", default=len(axes) or 2)
        axes = (axes or ["hook"])[:count]
        while len(axes) < count:
            axes.append(f"axis {len(axes) + 1}")

        return {
            "variants": [
                {
                    "hook_type": axis,
                    "headline": f"[demo] Headline that turns on “{axis}”",
                    "body": (
                        f"[demo] Two lines of body copy written so that {axis} is the "
                        "thing setting this variant apart from its siblings."
                    ),
                    "cta": f"[demo] Act now — {axis}",
                }
                for axis in axes
            ]
        }

    def _visuals(self, prompt: str) -> dict:
        count = self._int_after(prompt, r"exactly (\d+) briefs", default=2)
        headlines = re.findall(r"^Headline:\s*(.+)$", prompt, flags=re.MULTILINE)

        briefs = []
        for index in range(count):
            headline = headlines[index] if index < len(headlines) else "[demo] Headline"
            zone = ["top-left", "bottom-left", "top-center"][index % 3]
            treatment = ["bare", "soft-gradient", "glass-panel", "ribbon"][index % 4]
            briefs.append(
                {
                    "composition_notes": (
                        "[demo] Subject sits left of centre; the eye lands on the face "
                        "first and the headline occupies the open space above it."
                    ),
                    "image_prompt": (
                        f"[demo] Natural-light photograph, Malaysian setting, with "
                        f"clear uncluttered space at {zone} for a headline."
                    ),
                    "text_placement": (
                        f'[demo] "{headline}" at {zone}; the call to action sits '
                        "directly beneath it."
                    ),
                    "placement_zone": zone,
                    "text_treatment": treatment,
                }
            )
        return {"briefs": briefs}

    def _verdict(self) -> dict:
        """First review sends the work back, the second passes it.

        Rehearsing the happy path only would hide the revision cycle, which is
        the part of the graph worth watching.
        """
        self._reviews += 1
        if self._reviews % 2 == 1:
            return {
                "verdict": "revise_copy",
                "notes": (
                    "[demo] Variants 1 and 2 are the same idea in different words — "
                    "make the assigned axis actually change the copy."
                ),
            }
        return {"verdict": "pass", "notes": ""}

    def _qa(self) -> dict:
        """Every third asset comes back flagged.

        A rehearsal where QA always passes hides the redo loop, which is the
        part of this stage worth watching — the same reason `_verdict` sends
        the first crew review back.
        """
        self._checks = getattr(self, "_checks", 0) + 1
        if self._checks % 3 == 0:
            return {
                "status": "flagged",
                "notes": (
                    "[demo] The headline sits over the busiest part of the frame — "
                    "ask for cleaner space where it lands."
                ),
            }
        return {"status": "passed", "notes": ""}

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _citations(prompt: str) -> tuple[list[str], list[str]]:
        """Split the prompt's chunk ids by the heading they appeared under."""
        marker = prompt.find("## TREND SIGNALS")
        if marker == -1:
            return CHUNK.findall(prompt), []
        return CHUNK.findall(prompt[:marker]), CHUNK.findall(prompt[marker:])

    @staticmethod
    def _int_after(prompt: str, pattern: str, *, default: int) -> int:
        match = re.search(pattern, prompt)
        return int(match.group(1)) if match else default
