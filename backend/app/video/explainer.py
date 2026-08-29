"""The offline-first renderer for structured marketing videos.

This is deliberately a motion-graphics renderer, not a text-to-video prompt.
Product walkthroughs live or die on legible product UI and exact copy; those
are things a template renderer can guarantee while a generative video model
cannot. It gives the app a complete, reviewable MP4 pipeline without a key.
The public renderer boundary is also where a future live renderer can be
swapped in for cinematic B-roll without changing the API or review gate.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from textwrap import wrap
from typing import Literal

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.media.base import RenderError

WIDTH = 720
HEIGHT = 1280
FPS = 24
SCENE_SECONDS = 3


@dataclass(frozen=True)
class ExplainerScript:
    """The original fixed Agentcy demo contract, retained for compatibility."""

    title: str
    strapline: str
    cta: str


@dataclass(frozen=True)
class RenderedExplainer:
    """The review frame and final file from one completed render."""

    video: bytes
    poster: bytes
    duration_seconds: int
    scene_count: int


VideoSceneLayout = Literal["hero", "feature", "workflow", "proof", "cta"]


@dataclass(frozen=True)
class MarketingVideoScene:
    """One editable beat in a reusable, caption-led marketing video."""

    eyebrow: str
    headline: str
    body: str
    layout: VideoSceneLayout = "feature"


@dataclass(frozen=True)
class MarketingVideoScript:
    """Structured content for any product/explainer video in the studio.

    The default profile happens to describe Agentcy, but no string here is
    product-specific. A different brand, offer and sequence uses the same
    render → QA → review → export path.
    """

    brand_name: str
    product_name: str
    target_audience: str
    cta: str
    scenes: list[MarketingVideoScene]


#: Where the copy column ends and the footage is allowed to speak for itself.
COPY_FOOT = 620
#: Where the scrim has finished easing off and holds its lightest value.
SCRIM_FOOT = 880


def _shade_at(y: int) -> int:
    """How dark the scrim is on row `y`.

    Heavy enough through the copy column that white type reads over a white
    clip, then eased away so the footage below is not paid for and hidden.
    The values are derived, not chosen by eye: compositing (9, 12, 18) at
    alpha `a` over white lands at `255 - 242a/255`, so alpha 175 puts the
    background near luminance 89 against text at 244.
    """
    if y <= COPY_FOOT:
        # A slight lift down the column so the top edge does not read as a bar.
        return int(200 - 25 * (y / COPY_FOOT))
    if y <= SCRIM_FOOT:
        eased = (y - COPY_FOOT) / (SCRIM_FOOT - COPY_FOOT)
        return int(175 - 105 * eased)
    return 70


class ExplainerRenderer:
    """Renders a short vertical, structured marketing video with FFmpeg.

    Pillow draws high-contrast product scenes from a supplied storyboard.
    FFmpeg then turns them into an H.264 MP4, adding short fades between
    scenes. ``ExplainerScript`` remains supported for existing Agentcy demo
    videos; ``MarketingVideoScript`` is the reusable studio contract.
    """

    def __init__(
        self,
        *,
        ffmpeg_binary: str | None = None,
        fps: int = FPS,
        scene_seconds: int = SCENE_SECONDS,
        timeout_seconds: int = 90,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary or shutil.which("ffmpeg")
        self.fps = fps
        self.scene_seconds = scene_seconds
        self.timeout_seconds = timeout_seconds

    def render(
        self,
        script: ExplainerScript | MarketingVideoScript,
        *,
        backdrops: list[bytes] | None = None,
        product_image: bytes | None = None,
    ) -> RenderedExplainer:
        """Draw the storyboard and encode it.

        `backdrops` is one generated clip per scene. When given, the captions
        are drawn on transparency and composited over the clips instead of
        over the renderer's own painted background — see `app.video.broll`.
        The words are still drawn here either way; that is the whole point.
        """
        over_video = backdrops is not None
        scenes = (
            self._scenes(script, over_video=over_video)
            if isinstance(script, ExplainerScript)
            else self._marketing_scenes(
                script, over_video=over_video, product_image=product_image
            )
        )
        if over_video and len(backdrops) != len(scenes):
            raise RenderError(
                f"b-roll needs one clip per scene — got {len(backdrops)} "
                f"for {len(scenes)} scenes"
            )
        video = self._encode(scenes, backdrops=backdrops)
        # A transparent caption layer makes a near-empty poster, and the QA
        # pass would then be judging an empty frame. Take the poster from the
        # finished video, which is what a reviewer actually sees.
        poster = (
            self._poster_from_video(video) if over_video else self._png(scenes[-1])
        )
        return RenderedExplainer(
            video=video,
            poster=poster,
            duration_seconds=len(scenes) * self.scene_seconds,
            scene_count=len(scenes),
        )

    # -- story -------------------------------------------------------------

    def _scenes(
        self, script: ExplainerScript, *, over_video: bool = False
    ) -> list[Image.Image]:
        return [
            self._cover(script, over_video=over_video),
            self._brand_profile(over_video=over_video),
            self._brief(over_video=over_video),
            self._agents(over_video=over_video),
            self._review(over_video=over_video),
            self._outro(script, over_video=over_video),
        ]

    def _marketing_scenes(
        self,
        script: MarketingVideoScript,
        *,
        over_video: bool = False,
        product_image: bytes | None = None,
    ) -> list[Image.Image]:
        return [
            self._marketing_scene(
                script,
                scene,
                index,
                len(script.scenes),
                over_video=over_video,
                product_image=product_image,
            )
            for index, scene in enumerate(script.scenes)
        ]

    def _marketing_scene(
        self,
        script: MarketingVideoScript,
        scene: MarketingVideoScene,
        index: int,
        total: int,
        *,
        over_video: bool = False,
        product_image: bytes | None = None,
    ) -> Image.Image:
        image, draw = self._canvas(index % 6, over_video=over_video)
        self._eyebrow(
            draw,
            f"{self._short(script.brand_name, 30).upper()} · {scene.eyebrow.upper()}",
        )
        self._title(draw, scene.headline, top=180, max_lines=4)
        self._body(draw, scene.body, top=485, width=30)
        self._marketing_visual(draw, script, scene, top=755)
        if product_image:
            self._product_lock(image, product_image, top=755)
        self._page_number(draw, f"{index + 1:02d} / {total:02d}")
        return image

    def _marketing_visual(
        self,
        draw: ImageDraw.ImageDraw,
        script: MarketingVideoScript,
        scene: MarketingVideoScene,
        *,
        top: int,
    ) -> None:
        if scene.layout == "workflow":
            self._workflow_panel(draw, script, top=top)
            return
        if scene.layout == "proof":
            self._proof_panel(draw, script, top=top)
            return
        if scene.layout == "cta":
            self._cta_panel(draw, script, top=top)
            return
        if scene.layout == "hero":
            self._hero_panel(draw, script, top=top)
            return
        self._feature_panel(draw, script, scene, top=top)

    @staticmethod
    def _product_lock(image: Image.Image, product_bytes: bytes, *, top: int) -> None:
        """Place the marketer's source photo intact in every product scene."""
        try:
            product = Image.open(io.BytesIO(product_bytes)).convert("RGBA")
        except (OSError, ValueError):
            return
        product.thumbnail((250, 300), Image.Resampling.LANCZOS)
        if not product.width or not product.height:
            return
        x = WIDTH - product.width - 80
        y = min(top + 70, HEIGHT - product.height - 72)
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        pad = 18
        draw.rounded_rectangle(
            (x - pad, y - pad, x + product.width + pad, y + product.height + pad),
            radius=18,
            fill=(5, 9, 16, 170),
            outline=(190, 201, 220, 105),
            width=2,
        )
        shadow = Image.new("RGBA", product.size, (0, 0, 0, 130))
        shadow.putalpha(product.getchannel("A").filter(ImageFilter.GaussianBlur(12)))
        layer.alpha_composite(shadow, (x + 10, y + 14))
        layer.alpha_composite(product, (x, y))
        image.alpha_composite(layer)

    def _hero_panel(
        self, draw: ImageDraw.ImageDraw, script: MarketingVideoScript, *, top: int
    ) -> None:
        self._panel(draw, 48, top, 672, 1140)
        self._small_label(draw, 78, top + 48, "PRODUCT SNAPSHOT")
        draw.text(
            (78, top + 102),
            self._short(script.product_name, 28),
            font=self._font(35, bold=True),
            fill="#F4F7FB",
        )
        self._card_line(draw, 78, top + 190, 442)
        self._card_line(draw, 78, top + 238, 350)
        self._card_line(draw, 78, top + 286, 414)
        self._pill(draw, 78, top + 370, self._short(script.target_audience, 40))
        self._button(
            draw,
            78,
            top + 476,
            self._short(script.cta, 38).upper(),
            solid=True,
            width=500,
            height=64,
        )

    def _feature_panel(
        self,
        draw: ImageDraw.ImageDraw,
        script: MarketingVideoScript,
        scene: MarketingVideoScene,
        *,
        top: int,
    ) -> None:
        self._panel(draw, 48, top, 672, 1140)
        self._small_label(draw, 78, top + 48, "PRODUCT FEATURE")
        self._field(draw, 78, top + 112, "Brand", self._short(script.brand_name, 34))
        self._field(draw, 78, top + 202, "Product", self._short(script.product_name, 34))
        self._field(draw, 78, top + 292, "Focus", self._short(scene.eyebrow, 34))
        self._pill(draw, 78, top + 400, self._short(script.target_audience, 40))

    def _workflow_panel(
        self, draw: ImageDraw.ImageDraw, script: MarketingVideoScript, *, top: int
    ) -> None:
        self._panel(draw, 48, top, 672, 1140)
        self._small_label(draw, 78, top + 48, "HOW IT WORKS")
        steps = [
            ("01", "Start", "Set the direction"),
            ("02", "Make", "Turn it into work"),
            ("03", "Share", "Put it in motion"),
        ]
        for index, (number, title, detail) in enumerate(steps):
            y = top + 118 + index * 132
            draw.ellipse(
                (78, y, 126, y + 48), fill=("#8BE0C0", "#BFC9FA", "#E0BFF4")[index]
            )
            draw.text((91, y + 13), number, font=self._font(13, bold=True), fill="#17202B")
            draw.text((150, y), title, font=self._font(27, bold=True), fill="#F4F7FB")
            draw.text((150, y + 36), detail, font=self._font(17), fill="#B4C2D0")
        self._pill(draw, 78, top + 540, self._short(script.product_name, 40))

    def _proof_panel(
        self, draw: ImageDraw.ImageDraw, script: MarketingVideoScript, *, top: int
    ) -> None:
        self._panel(draw, 48, top, 672, 1140)
        self._small_label(draw, 78, top + 48, "WHY IT LANDS")
        self._status(draw, 78, top + 118, "CLEAR MESSAGE")
        self._status(draw, 78, top + 186, "PRODUCT IN FOCUS")
        self._status(draw, 78, top + 254, "READY TO SHARE")
        self._pill(draw, 78, top + 370, self._short(script.target_audience, 40))

    def _cta_panel(
        self, draw: ImageDraw.ImageDraw, script: MarketingVideoScript, *, top: int
    ) -> None:
        self._panel(draw, 48, top, 672, 1140)
        self._small_label(draw, 78, top + 48, self._short(script.brand_name, 34).upper())
        draw.text(
            (78, top + 120),
            self._short(script.product_name, 28),
            font=self._font(34, bold=True),
            fill="#F4F7FB",
        )
        self._button(
            draw,
            78,
            top + 260,
            self._short(script.cta, 42).upper(),
            solid=True,
            width=520,
            height=72,
        )
        self._pill(draw, 78, top + 390, self._short(script.target_audience, 40))

    def _cover(
        self, script: ExplainerScript, *, over_video: bool = False
    ) -> Image.Image:
        image, draw = self._canvas(0, over_video=over_video)
        self._eyebrow(draw, "AGENTCY · YOUR MARKETING TEAM, ON DEMAND")
        self._title(draw, script.title, top=252, max_lines=4)
        self._body(draw, script.strapline, top=610, width=26)
        if over_video:
            return image
        self._phone(draw, 48, 766, step="01", title="From a brief", detail="to a campaign")
        self._page_number(draw, "01 / 06")
        return image

    def _brand_profile(self, *, over_video: bool = False) -> Image.Image:
        image, draw = self._canvas(1, over_video=over_video)
        self._eyebrow(draw, "01 · START WITH WHAT IS TRUE")
        self._title(draw, "Set your brand profile.", top=145, max_lines=3)
        self._body(
            draw,
            "Your company, products, claims and guardrails become the source every agent works from.",
            top=405,
            width=30,
        )
        if over_video:
            return image
        self._panel(draw, 48, 690, 672, 1110)
        self._small_label(draw, 78, 735, "BRAND PROFILE")
        self._field(draw, 78, 792, "Company", "Kawan Kopi")
        self._field(draw, 78, 882, "Product", "Rumah Blend")
        self._field(draw, 78, 972, "Guardrail", "Only approved claims")
        self._page_number(draw, "02 / 06")
        return image

    def _brief(self, *, over_video: bool = False) -> Image.Image:
        image, draw = self._canvas(2, over_video=over_video)
        self._eyebrow(draw, "02 · SHARE THE GOAL")
        self._title(draw, "Write one clear brief.", top=145, max_lines=3)
        self._body(
            draw,
            "Tell Agentcy what needs to move. It finds the useful signal, then turns it into a focused plan.",
            top=405,
            width=30,
        )
        if over_video:
            return image
        self._panel(draw, 48, 690, 672, 1110)
        self._small_label(draw, 78, 735, "CAMPAIGN BRIEF")
        self._card_line(draw, 78, 795, 490)
        self._card_line(draw, 78, 843, 410)
        self._card_line(draw, 78, 891, 462)
        self._pill(draw, 78, 966, "Audience: urban home brewers")
        self._pill(draw, 78, 1020, "Goal: launch the new blend")
        self._page_number(draw, "03 / 06")
        return image

    def _agents(self, *, over_video: bool = False) -> Image.Image:
        image, draw = self._canvas(3, over_video=over_video)
        self._eyebrow(draw, "03 · LET THE TEAM MAKE")
        self._title(draw, "Four agents, one connected workflow.", top=145, max_lines=4)
        self._body(
            draw,
            "Planner, copywriter, visual planner and director each do their part — with the same grounded context.",
            top=465,
            width=30,
        )
        if over_video:
            return image
        nodes = [
            (84, 730, "Plan", "Find the angle"),
            (378, 730, "Write", "Shape the words"),
            (84, 940, "Visualise", "Brief the creative"),
            (378, 940, "Direct", "Keep it distinct"),
        ]
        for index, (x, y, title, detail) in enumerate(nodes):
            self._agent_node(draw, x, y, title, detail, index)
        self._page_number(draw, "04 / 06")
        return image

    def _review(self, *, over_video: bool = False) -> Image.Image:
        image, draw = self._canvas(4, over_video=over_video)
        self._eyebrow(draw, "04 · REVIEW BEFORE IT LEAVES")
        self._title(draw, "See the work. Keep the decision.", top=145, max_lines=4)
        self._body(
            draw,
            "Vision QA checks the creative first. You approve, reject or ask for another pass before export.",
            top=465,
            width=30,
        )
        if over_video:
            return image
        self._panel(draw, 48, 735, 672, 1090)
        self._small_label(draw, 78, 778, "REVIEW GATE")
        self._creative_preview(draw, 78, 830)
        self._status(draw, 442, 855, "QA PASSED")
        self._button(draw, 442, 940, "APPROVE", solid=True)
        self._button(draw, 442, 1004, "REDO", solid=False)
        self._page_number(draw, "05 / 06")
        return image

    def _outro(
        self, script: ExplainerScript, *, over_video: bool = False
    ) -> Image.Image:
        image, draw = self._canvas(5, over_video=over_video)
        self._eyebrow(draw, "AGENTCY · MAKE THE NEXT CAMPAIGN")
        self._title(draw, script.cta, top=245, max_lines=4)
        self._body(
            draw,
            "Grounded strategy, reviewable creative and a workflow your team can actually run.",
            top=610,
            width=30,
        )
        self._button(draw, 48, 950, "OPEN AGENTCY", solid=True, width=624, height=74)
        if over_video:
            return image
        self._page_number(draw, "06 / 06")
        return image

    # -- drawing primitives ------------------------------------------------

    def _canvas(
        self, scene: int, *, over_video: bool = False
    ) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        if over_video:
            return self._scrim()
        palettes = [
            ("#10131C", "#26465B", "#BFDBC4"),
            ("#10141D", "#413D70", "#D7CCF4"),
            ("#111720", "#2A604E", "#BDE9D1"),
            ("#15131D", "#684B84", "#E4CFF7"),
            ("#11161E", "#485A6D", "#C7D7EA"),
            ("#0F141C", "#385D64", "#D0EBCA"),
        ]
        base, accent, glow = palettes[scene]
        image = Image.new("RGB", (WIDTH, HEIGHT), base)
        draw = ImageDraw.Draw(image)
        draw.ellipse((360, -200, 1040, 480), fill=accent)
        draw.ellipse((-380, 820, 330, 1510), fill="#1A2431")
        draw.ellipse((448, 940, 830, 1322), fill=glow)
        draw.rectangle((0, 0, WIDTH, HEIGHT), outline="#FFFFFF", width=1)
        return image, draw

    @staticmethod
    def _scrim() -> tuple[Image.Image, ImageDraw.ImageDraw]:
        """A transparent canvas with just enough shade to keep text readable.

        Generated b-roll is unpredictable — a bright sky behind white type is
        unreadable, and re-rolling the clip is slow and paid. A fixed scrim,
        heaviest where the copy sits, makes legibility a property of the
        renderer rather than a gamble on the clip. It stays translucent
        throughout: an opaque scrim would hide the video it sits on.
        """
        image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        shade = ImageDraw.Draw(image)
        # Written once per row and never twice. `ImageDraw` *replaces* pixels
        # on an RGBA image rather than blending into them, so a base wash laid
        # down first and then crossed by a ramp does not add up — the ramp wins
        # outright. The previous scrim did exactly that and lost its wash
        # behind the body copy, which is why white text over a bright clip came
        # out at the same luminance as the clip.
        for y in range(HEIGHT):
            shade.rectangle((0, y, WIDTH, y), fill=(9, 12, 18, _shade_at(y)))
        return image, ImageDraw.Draw(image)

    def _eyebrow(self, draw: ImageDraw.ImageDraw, text: str) -> None:
        draw.text((48, 72), text, font=self._font(17, bold=True), fill="#C6D3E2")

    def _title(
        self, draw: ImageDraw.ImageDraw, text: str, *, top: int, max_lines: int
    ) -> None:
        lines = self._wrap(text, width=17, max_lines=max_lines)
        font = self._font(56, bold=True)
        y = top
        for line in lines:
            draw.text((48, y), line, font=font, fill="#F4F7FB")
            y += 66

    def _body(self, draw: ImageDraw.ImageDraw, text: str, *, top: int, width: int) -> None:
        font = self._font(24)
        y = top
        for line in self._wrap(text, width=width, max_lines=5):
            draw.text((48, y), line, font=font, fill="#D3DCE8")
            y += 35

    def _panel(
        self, draw: ImageDraw.ImageDraw, left: int, top: int, right: int, bottom: int
    ) -> None:
        draw.rounded_rectangle(
            (left, top, right, bottom), radius=28, fill="#131B27", outline="#AABDCF", width=2
        )

    def _phone(
        self, draw: ImageDraw.ImageDraw, left: int, top: int, *, step: str, title: str, detail: str
    ) -> None:
        self._panel(draw, left, top, 672, 1160)
        draw.rounded_rectangle((left + 24, top + 28, 648, top + 122), radius=14, fill="#263745")
        self._small_label(draw, left + 46, top + 56, f"{step}  {title.upper()}")
        draw.text((left + 46, top + 165), detail, font=self._font(32, bold=True), fill="#F4F7FB")
        for index, width in enumerate((340, 270, 320)):
            draw.rounded_rectangle(
                (left + 46, top + 250 + index * 66, left + 46 + width, top + 270 + index * 66),
                radius=10,
                fill="#415265",
            )
        self._button(draw, left + 46, top + 485, "BUILD CAMPAIGN", solid=True, width=388)

    def _small_label(self, draw: ImageDraw.ImageDraw, x: int, y: int, text: str) -> None:
        draw.text((x, y), text, font=self._font(16, bold=True), fill="#BFD1E2")

    def _field(self, draw: ImageDraw.ImageDraw, x: int, y: int, label: str, value: str) -> None:
        draw.text((x, y), label.upper(), font=self._font(15, bold=True), fill="#8EA1B5")
        draw.text((x, y + 28), value, font=self._font(23), fill="#F0F4FA")
        draw.line((x, y + 70, 600, y + 70), fill="#334658", width=2)

    def _card_line(self, draw: ImageDraw.ImageDraw, x: int, y: int, width: int) -> None:
        draw.rounded_rectangle((x, y, x + width, y + 18), radius=8, fill="#425568")

    def _pill(self, draw: ImageDraw.ImageDraw, x: int, y: int, text: str) -> None:
        font = self._font(17)
        box = draw.textbbox((x, y), text, font=font)
        draw.rounded_rectangle((x - 10, y - 8, box[2] + 12, y + 30), radius=18, fill="#294856")
        draw.text((x, y), text, font=font, fill="#DDEBF4")

    def _agent_node(
        self, draw: ImageDraw.ImageDraw, x: int, y: int, title: str, detail: str, index: int
    ) -> None:
        draw.rounded_rectangle((x, y, x + 258, y + 156), radius=24, fill="#182432", outline="#A0B5C9", width=2)
        draw.ellipse((x + 24, y + 24, x + 72, y + 72), fill=("#92E6C7", "#BFC9FA", "#E0BFF4", "#C0DBEE")[index])
        draw.text((x + 24, y + 94), title, font=self._font(24, bold=True), fill="#F4F7FB")
        draw.text((x + 24, y + 126), detail, font=self._font(16), fill="#B4C2D0")

    def _creative_preview(self, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        draw.rounded_rectangle((x, y, x + 312, y + 180), radius=18, fill="#446872")
        draw.ellipse((x + 180, y + 36, x + 304, y + 160), fill="#94CCB3")
        draw.rectangle((x + 22, y + 24, x + 176, y + 38), fill="#EFF6F8")
        draw.rectangle((x + 22, y + 52, x + 136, y + 64), fill="#D9E7EB")
        draw.rounded_rectangle((x + 22, y + 124, x + 154, y + 154), radius=14, fill="#18343A")

    def _status(self, draw: ImageDraw.ImageDraw, x: int, y: int, text: str) -> None:
        draw.ellipse((x, y, x + 14, y + 14), fill="#79D9B2")
        draw.text((x + 25, y - 5), text, font=self._font(16, bold=True), fill="#CFECE1")

    def _button(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        text: str,
        *,
        solid: bool,
        width: int = 178,
        height: int = 48,
    ) -> None:
        fill = "#EDF5F7" if solid else "#263847"
        color = "#101820" if solid else "#D9E5EF"
        draw.rounded_rectangle((x, y, x + width, y + height), radius=14, fill=fill, outline="#D5E1EA", width=1)
        draw.text((x + 18, y + (height - 18) // 2), text, font=self._font(15, bold=True), fill=color)

    def _page_number(self, draw: ImageDraw.ImageDraw, text: str) -> None:
        draw.text((48, 1202), text, font=self._font(15, bold=True), fill="#AEBED0")

    @staticmethod
    def _wrap(text: str, *, width: int, max_lines: int) -> list[str]:
        words = " ".join(text.split()) or "Agentcy"
        lines = wrap(words, width=width, break_long_words=False, break_on_hyphens=False)
        if len(lines) <= max_lines:
            return lines
        clipped = lines[:max_lines]
        clipped[-1] = clipped[-1].rstrip(".,;: ") + "…"
        return clipped

    @staticmethod
    def _short(text: str, limit: int) -> str:
        """Keep UI labels inside the deterministic canvas rather than spilling.

        Full user-entered wording still appears in the API and video record;
        this only bounds a single line in the on-screen product mock-up.
        """
        normalized = " ".join(text.split())
        return normalized if len(normalized) <= limit else normalized[: limit - 1].rstrip() + "…"

    @staticmethod
    def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        # These are the image paths in Debian and common macOS installations.
        for directory in (
            "/usr/share/fonts/truetype/dejavu",
            "/Library/Fonts",
            "/System/Library/Fonts/Supplemental",
        ):
            candidate = Path(directory) / name
            if candidate.is_file():
                return ImageFont.truetype(candidate, size=size)
        return ImageFont.load_default()

    @staticmethod
    def _png(image: Image.Image) -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    # -- encoding ----------------------------------------------------------

    def _broll_filtergraph(self, count: int) -> str:
        """The filter chain that puts the drawn captions over the clips.

        Inputs alternate clip, caption, clip, caption… so scene `i` reads
        inputs `2i` and `2i+1`. The clip is scaled up and cropped rather than
        padded: a 16:9 clip padded into a 9:16 frame leaves black bars behind
        the captions, which looks like a bug rather than a choice.
        """
        fade_at = max(0, self.scene_seconds - 0.35)
        filters: list[str] = []
        labels: list[str] = []
        for index in range(count):
            clip, caption = index * 2, index * 2 + 1
            filters.append(
                f"[{clip}:v]fps={self.fps},"
                f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},setsar=1,"
                f"trim=duration={self.scene_seconds},setpts=PTS-STARTPTS[bg{index}]"
            )
            filters.append(f"[{caption}:v]scale={WIDTH}:{HEIGHT},setsar=1[cap{index}]")
            filters.append(
                f"[bg{index}][cap{index}]overlay=0:0:format=auto,"
                f"fade=t=in:st=0:d=0.35,fade=t=out:st={fade_at}:d=0.35[v{index}]"
            )
            labels.append(f"[v{index}]")
        filters.append("".join(labels) + f"concat=n={count}:v=1:a=0[out]")
        return ";".join(filters)

    def _poster_from_video(self, video: bytes) -> bytes:
        """The review frame, taken from the encoded video itself.

        Only used on the b-roll path, where the drawn scene is transparent and
        would make a poster of almost nothing.
        """
        if not self.ffmpeg_binary:
            raise RenderError(
                "Video rendering needs FFmpeg. Install it locally, or run Agentcy in Docker."
            )
        with tempfile.TemporaryDirectory(prefix="agentcy-poster-") as temporary:
            root = Path(temporary)
            source = root / "video.mp4"
            source.write_bytes(video)
            frame = root / "poster.png"
            # Just before the final fade-out, so the closing scene is legible.
            at = max(0.0, self.scene_seconds - 0.5)
            result = subprocess.run(
                [self.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error",
                 "-sseof", f"-{self.scene_seconds}", "-i", str(source),
                 "-ss", str(at), "-frames:v", "1", str(frame)],
                check=False, capture_output=True, text=True,
                timeout=self.timeout_seconds,
            )
            if result.returncode != 0 or not frame.is_file():
                detail = (result.stderr or "unknown FFmpeg error").strip()
                raise RenderError(f"Could not take a poster frame: {detail}")
            return frame.read_bytes()

    def _encode(
        self, scenes: list[Image.Image], backdrops: list[bytes] | None = None
    ) -> bytes:
        if not self.ffmpeg_binary:
            raise RenderError(
                "Video rendering needs FFmpeg. Install it locally, or run Agentcy in Docker."
            )
        if backdrops:
            return self._encode_over_broll(scenes, backdrops)

        with tempfile.TemporaryDirectory(prefix="agentcy-explainer-") as temporary:
            root = Path(temporary)
            inputs: list[Path] = []
            for index, scene in enumerate(scenes):
                frame = root / f"scene-{index:02d}.png"
                scene.save(frame, format="PNG")
                inputs.append(frame)
            output = root / "agentcy-explainer.mp4"

            command = [self.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error"]
            for frame in inputs:
                command.extend(["-loop", "1", "-t", str(self.scene_seconds), "-i", str(frame)])

            filters: list[str] = []
            labels: list[str] = []
            fade_at = max(0, self.scene_seconds - 0.35)
            for index in range(len(inputs)):
                label = f"v{index}"
                labels.append(f"[{label}]")
                filters.append(
                    f"[{index}:v]fps={self.fps},scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
                    f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                    f"fade=t=in:st=0:d=0.35,fade=t=out:st={fade_at}:d=0.35[{label}]"
                )
            filters.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[out]")
            command.extend(
                [
                    "-filter_complex",
                    ";".join(filters),
                    "-map",
                    "[out]",
                    "-r",
                    str(self.fps),
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(output),
                ]
            )

            try:
                result = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                )
            except OSError as error:
                raise RenderError(f"Could not start FFmpeg: {error}") from error
            except subprocess.TimeoutExpired as error:
                raise RenderError("Video rendering timed out before it finished.") from error

            if result.returncode != 0 or not output.exists():
                detail = (result.stderr or result.stdout or "unknown FFmpeg error").strip()
                raise RenderError(f"FFmpeg could not render the explainer video: {detail}")
            return output.read_bytes()

    def _encode_over_broll(
        self, scenes: list[Image.Image], backdrops: list[bytes]
    ) -> bytes:
        """Composite the caption layers over the generated clips."""
        with tempfile.TemporaryDirectory(prefix="agentcy-broll-") as temporary:
            root = Path(temporary)
            command = [self.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error"]
            for index, (scene, clip) in enumerate(zip(scenes, backdrops)):
                clip_path = root / f"clip-{index:02d}.mp4"
                clip_path.write_bytes(clip)
                caption_path = root / f"caption-{index:02d}.png"
                scene.save(caption_path, format="PNG")
                command.extend(["-i", str(clip_path)])
                command.extend(
                    ["-loop", "1", "-t", str(self.scene_seconds), "-i", str(caption_path)]
                )

            output = root / "agentcy-broll.mp4"
            command.extend(
                [
                    "-filter_complex", self._broll_filtergraph(len(scenes)),
                    "-map", "[out]",
                    "-r", str(self.fps),
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    str(output),
                ]
            )
            try:
                result = subprocess.run(
                    command, check=False, capture_output=True, text=True,
                    timeout=self.timeout_seconds,
                )
            except OSError as error:
                raise RenderError(f"Could not start FFmpeg: {error}") from error
            except subprocess.TimeoutExpired as error:
                raise RenderError("Video rendering timed out before it finished.") from error

            if result.returncode != 0 or not output.exists():
                detail = (result.stderr or result.stdout or "unknown FFmpeg error").strip()
                raise RenderError(f"FFmpeg could not composite the b-roll video: {detail}")
            return output.read_bytes()
