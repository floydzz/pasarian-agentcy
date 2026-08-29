"""The render-and-review service for Agentcy's own product film."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.agents.vision_qa import VisionQA
from app.domain import VisualBrief
from app.media.storage import AssetStorage
from app.video import ExplainerRenderer, ExplainerScript
from app.video.broll import BrollProvider

log = logging.getLogger(__name__)

# The poster is a whole scene, not a representative AI image.  It still runs
# through the same QA contract as a campaign creative, so a human can see the
# automated verdict before exporting the film.
#: The label on the closing frame's button. Fixed by `_outro`, not by the
#: spec, so QA is told the words that are really on the poster.
OUTRO_BUTTON = "OPEN AGENTCY"

DEMO_VIDEO_BRIEF = VisualBrief(
    composition_notes="High-contrast vertical product walkthrough with captions and software UI.",
    image_prompt="Agentcy product-explainer closing scene with an uncluttered call to action.",
    text_placement="Headline in the upper half and a clear call to action in the centre.",
    placement_zone="top-left",
)


#: What each of the film's six fixed scenes should have moving behind it.
#: One entry per scene, in the order `ExplainerRenderer._scenes` builds them:
#: cover, brand profile, brief, agents, review, outro. The film's structure is
#: fixed, so these are too — a b-roll run always costs exactly six clips.
SCENE_MOODS = (
    "a bright modern studio desk at dawn, a laptop closed beside a notebook",
    "hands arranging fabric swatches and product samples on a pale surface",
    "a quiet office window with morning light falling across an empty desk",
    "abstract soft-focus light moving across a dark surface, slow drift",
    "a person leaning back reviewing something off-camera, warm side light",
    "a calm wide shot of an empty creative studio, late afternoon light",
)


@dataclass(frozen=True)
class DemoVideoSpec:
    title: str
    strapline: str
    cta: str
    #: Generate a clip behind every scene. Off by default: the film renders
    #: completely without it, and turning it on spends six clips of paid quota.
    use_broll: bool = False


@dataclass(frozen=True)
class RenderedDemoVideo:
    media_url: str
    poster_url: str
    duration_seconds: int
    scene_count: int
    qa_status: str
    qa_notes: str | None


class DemoVideoStudio:
    """Create a complete MP4, then QA its poster before human review."""

    def __init__(
        self,
        *,
        renderer: ExplainerRenderer,
        qa: VisionQA,
        storage: AssetStorage,
        broll: BrollProvider | None = None,
    ) -> None:
        self.renderer = renderer
        self.qa = qa
        self.storage = storage
        self.broll = broll

    # -- b-roll ------------------------------------------------------------

    @staticmethod
    def broll_prompt(mood: str) -> str:
        """What the video model is asked for: the background, and only that.

        Every word in the finished frame is drawn by the renderer, so the clip
        must not contain any of its own — generated lettering is the exact
        failure the caption layer exists to avoid, and unlike a bad crop it
        cannot be corrected without paying for another clip.
        """
        return (
            f"Cinematic vertical b-roll: {mood}. "
            "Real footage, shallow depth of field, soft natural light, "
            "slow camera move, uncluttered composition with empty space in "
            "the upper half and lower third. "
            "No text, no letters, no words, no captions, no logos, no watermarks."
        )

    def _backdrops(self, spec: DemoVideoSpec) -> list[bytes] | None:
        """One clip per scene, or None to fall back to the painted render.

        Degrading rather than failing matches the vision QA pass and the
        marketing studio: the painted film is complete and shippable, so a
        vendor outage should cost the run its backdrops, not its output. A
        partial set is discarded rather than padded — the renderer requires one
        clip per scene, and half a film over video is not a thing worth making.
        """
        if not spec.use_broll or self.broll is None:
            return None

        clips: list[bytes] = []
        for mood in SCENE_MOODS:
            try:
                clips.append(
                    self.broll.render_clip(self.broll_prompt(mood), aspect="9:16")
                )
            except Exception as error:
                # Deliberately broad: a vendor SDK may raise anything, and the
                # fallback is a complete film either way. Logged rather than
                # swallowed: this route has no event stream and returns the
                # same 200 whether or not the backdrops arrived, so without
                # this line a refused run is indistinguishable from a good one.
                log.warning(
                    "b-roll unavailable, rendering the painted film instead: %s",
                    error,
                )
                return None
        return clips

    def run(self, spec: DemoVideoSpec) -> RenderedDemoVideo:
        rendered = self.renderer.render(
            ExplainerScript(
                title=spec.title,
                strapline=spec.strapline,
                cta=spec.cta,
            ),
            backdrops=self._backdrops(spec),
        )
        # The poster is the closing frame — `scenes[-1]` painted, the last
        # video frame over b-roll — and that scene draws `spec.cta` as its
        # headline above a fixed OPEN AGENTCY button. Passing `spec.title`
        # here asked QA to check the frame against words five scenes earlier.
        verdict = self.qa.review(
            rendered.poster,
            headline=spec.cta,
            cta=OUTRO_BUTTON,
            brief=DEMO_VIDEO_BRIEF,
        )

        media_url = self.storage.save(rendered.video, suffix=".mp4")
        try:
            poster_url = self.storage.save(rendered.poster, suffix=".png")
        except Exception:
            # Do not leave an unreachable MP4 if the paired review image cannot
            # be written. Storage cannot be helpful without the preview.
            self.storage.path_for(media_url).unlink(missing_ok=True)
            raise

        return RenderedDemoVideo(
            media_url=media_url,
            poster_url=poster_url,
            duration_seconds=rendered.duration_seconds,
            scene_count=rendered.scene_count,
            qa_status=verdict.status,
            qa_notes=verdict.notes or None,
        )
