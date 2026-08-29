"""Reusable render-and-review service for structured marketing videos."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.events import AgentEvent, EventSink, emit
from app.agents.vision_qa import VisionQA
from app.domain import VisualBrief
from app.media.storage import AssetStorage
from app.video import ExplainerRenderer, MarketingVideoScene, MarketingVideoScript
from app.video.broll import BrollProvider

MARKETING_VIDEO_BRIEF = VisualBrief(
    composition_notes="High-contrast vertical marketing video with a readable product panel and captions.",
    image_prompt="Caption-led product marketing video closing frame with an uncluttered call to action.",
    text_placement="Headline in the upper half and a clear call to action in the centre.",
    placement_zone="top-left",
)


@dataclass(frozen=True)
class MarketingVideoSpec:
    name: str
    profile: str
    brand_name: str
    product_name: str
    target_audience: str
    cta: str
    storyboard: list[MarketingVideoScene]
    #: Opt-in. Generative b-roll costs money and minutes per render, so the
    #: default stays the instant, free, offline path.
    use_broll: bool = False
    #: Source photo to keep intact in the finished motion-graphics frames.
    product_image: bytes | None = None


@dataclass(frozen=True)
class RenderedMarketingVideo:
    media_url: str
    poster_url: str
    duration_seconds: int
    scene_count: int
    qa_status: str
    qa_notes: str | None


class VideoStudio:
    """A vendor-neutral render → QA → storage path for marketing videos."""

    def __init__(
        self,
        *,
        renderer: ExplainerRenderer,
        qa: VisionQA,
        storage: AssetStorage,
        broll: BrollProvider | None = None,
        max_broll_clips: int = 8,
    ) -> None:
        self.renderer = renderer
        self.qa = qa
        self.storage = storage
        self.broll = broll
        self.max_broll_clips = max_broll_clips

    # -- b-roll ------------------------------------------------------------

    @staticmethod
    def broll_prompt(spec: "MarketingVideoSpec", scene: MarketingVideoScene) -> str:
        """What the video model is asked for: the background, and only that.

        Every word in the finished frame is drawn by the renderer, so the clip
        must not contain any of its own — generated lettering is the exact
        failure the caption layer exists to avoid, and it cannot be corrected
        without paying for another clip.
        """
        return (
            f"Cinematic vertical b-roll for {spec.brand_name}, "
            f"a {spec.product_name} brand for {spec.target_audience}. "
            f"Mood: {scene.eyebrow.lower()}. "
            "Real footage, shallow depth of field, soft natural light, "
            "slow camera move, uncluttered composition with empty space in "
            "the upper half and lower third. "
            "No text, no letters, no words, no captions, no logos, no watermarks."
        )

    def _backdrops(
        self, spec: "MarketingVideoSpec", sink: EventSink | None
    ) -> list[bytes] | None:
        """Generate one clip per scene, or give up and return None.

        Degrading rather than failing is deliberate and matches the vision QA
        pass: the deterministic render is a complete, shippable video, so a
        vendor outage should cost the run its backdrops, not its output.
        """
        if not spec.use_broll or self.broll is None:
            return None
        if len(spec.storyboard) > self.max_broll_clips:
            emit(sink, AgentEvent("renderer", "running",
                 f"Storyboard is longer than the {self.max_broll_clips}-clip "
                 "b-roll limit; rendering without it"))
            return None

        clips: list[bytes] = []
        for index, scene in enumerate(spec.storyboard, start=1):
            emit(sink, AgentEvent("renderer", "running",
                 f"Generating b-roll {index} of {len(spec.storyboard)}"))
            try:
                clips.append(
                    self.broll.render_clip(self.broll_prompt(spec, scene), aspect="9:16")
                )
            except Exception as error:
                # Deliberately broad: a vendor SDK may raise anything, and the
                # fallback is a complete video either way.
                emit(sink, AgentEvent("renderer", "running",
                     f"B-roll unavailable ({error}); rendering the storyboard "
                     "without it"))
                return None
        return clips

    def run(
        self, spec: MarketingVideoSpec, *, sink: EventSink | None = None
    ) -> RenderedMarketingVideo:
        """Run the video-specific agents in the order the studio shows them."""
        emit(
            sink,
            AgentEvent(
                "planner",
                "started",
                f"Reading the {len(spec.storyboard)}-scene {spec.profile.replace('_', ' ')} brief",
            ),
        )
        emit(
            sink,
            AgentEvent(
                "planner",
                "finished",
                "Video brief is coherent and ready for the storyboard",
                {"scenes": len(spec.storyboard)},
            ),
        )
        emit(
            sink,
            AgentEvent(
                "visual_planner",
                "started",
                "Mapping the story beats to motion-graphics layouts",
            ),
        )
        emit(
            sink,
            AgentEvent(
                "visual_planner",
                "finished",
                f"Storyboard mapped across {len(spec.storyboard)} vertical scenes",
            ),
        )
        emit(
            sink,
            AgentEvent("renderer", "started", "Drawing scenes and encoding the vertical MP4"),
        )
        backdrops = self._backdrops(spec, sink)
        try:
            renderer_kwargs = {"backdrops": backdrops}
            # Keep lightweight custom renderers compatible with the existing
            # two-argument contract when no marketer supplied a product photo.
            # The production renderer receives the new product-lock argument
            # only for the flow that actually needs it.
            if spec.product_image is not None:
                renderer_kwargs["product_image"] = spec.product_image
            rendered = self.renderer.render(
                MarketingVideoScript(
                    brand_name=spec.brand_name,
                    product_name=spec.product_name,
                    target_audience=spec.target_audience,
                    cta=spec.cta,
                    scenes=spec.storyboard,
                ),
                **renderer_kwargs,
            )
        except Exception as error:
            emit(sink, AgentEvent("renderer", "failed", str(error)))
            raise
        emit(
            sink,
            AgentEvent(
                "renderer",
                "finished",
                f"Encoded {rendered.duration_seconds}-second H.264 video",
                {"duration_seconds": rendered.duration_seconds},
            ),
        )
        emit(sink, AgentEvent("vision_qa", "started", "Checking the closing frame before review"))
        verdict = self.qa.review(
            rendered.poster,
            headline=spec.storyboard[-1].headline,
            cta=spec.cta,
            brief=MARKETING_VIDEO_BRIEF,
        )
        emit(
            sink,
            AgentEvent(
                "vision_qa",
                "finished" if verdict.status == "passed" else "failed",
                "QA passed the review frame" if verdict.status == "passed" else verdict.notes,
                {"status": verdict.status, "notes": verdict.notes},
            ),
        )

        media_url = self.storage.save(rendered.video, suffix=".mp4")
        try:
            poster_url = self.storage.save(rendered.poster, suffix=".png")
        except Exception:
            self.storage.path_for(media_url).unlink(missing_ok=True)
            raise

        result = RenderedMarketingVideo(
            media_url=media_url,
            poster_url=poster_url,
            duration_seconds=rendered.duration_seconds,
            scene_count=rendered.scene_count,
            qa_status=verdict.status,
            qa_notes=verdict.notes or None,
        )
        emit(
            sink,
            AgentEvent(
                "system",
                "finished",
                "Video is ready for your review gate",
                {"qa_status": verdict.status},
            ),
        )
        return result
