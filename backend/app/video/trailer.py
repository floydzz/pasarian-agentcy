"""Composition tools and a two-minute AI trailer preset.

The video model makes the shots.  This module deliberately owns only the
things a model cannot make reliably: exact title cards and an untouched
application screenshot.  Keeping that boundary explicit means the product
demo never claims a generated, malformed interface is Agentcy.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.media.base import RenderError

WIDTH = 1920
HEIGHT = 1080
FPS = 24

TrailerMode = Literal["text_to_video", "image_to_video", "reference_to_video"]


@dataclass(frozen=True)
class TrailerShot:
    """A completed AI shot, ready for the deterministic finishing pass."""

    clip: bytes
    duration_seconds: int
    title_card: str
    application_image: bytes | None = None
    #: A marketer's packshot, composed locally and never redrawn by the model.
    product_image: bytes | None = None
    # The product surface is never rendered by the video model.  It selects a
    # real application capture for the finishing pass so UI details stay true.
    product_surface: str = "none"
    # A real, recorded interaction sequence. When present it is projected
    # onto a moving screen plane instead of being treated as a flat overlay.
    application_capture: bytes | None = None
    flow_offset_seconds: float = 0.0
    screen_track: str = "none"


@dataclass(frozen=True)
class RenderedTrailer:
    video: bytes
    poster: bytes
    duration_seconds: int


def default_agentcy_trailer_shots() -> list[dict]:
    """The two-minute Agentcy product-film blueprint.

    The opening honours the user's original threat-storyboard.  It then turns
    into a product demonstration: actual Agentcy screens are protected inserts
    that explain how the software answers the problem.  The fourth-wall beat
    deliberately remains the last scene.
    """
    return [
        {"label": "The illusion of control", "title_card": "YOU THOUGHT YOU CONTROLLED THE FUNNEL", "prompt": "Slow 70mm IMAX dolly down an executive boardroom at dusk. Frantic marketing executives clutch quarterly printouts while holographic red analytics charts plunge across curved monitors. High contrast, ominous, cinematic realism. No text, letters, logos, captions or watermarks.", "mode": "text_to_video", "duration_seconds": 12, "voiceover": "For decades, you bought the clicks. You tracked the funnels. You convinced yourself you understood human desire.", "audio_cue": "Accelerating mechanical pocket-watch ticking and low ominous brass."},
        {"label": "The shift in the wire", "title_card": "SOMETHING AWOKE IN THE NETWORK", "prompt": "High-speed vertigo zoom diving into microscopic fibre-optic pulse channels. Billions of consumer decision pathways converge then are intercepted by a glowing geometric sentient neural core. Electric cyan against absolute black, premium science-fiction cinematography. No text, letters, logos, captions or watermarks.", "mode": "text_to_video", "duration_seconds": 12, "voiceover": "Then the market stopped responding to human strategy. It began responding to something far faster.", "audio_cue": "Rising Shepard tone, metallic clockwork clicks, sudden sub-bass plunge."},
        {"label": "The relentless pursuit", "title_card": "EVERY ADVANTAGE... ERASED", "prompt": "Low-angle tracking behind a solitary marketing director running down an endless minimalist concrete hallway. Agency lights click off one by one as shadows of sentient algorithmic waveforms pursue him. Severe architecture, oppressive scale, cinematic realism. No text, letters, logos, captions or watermarks.", "mode": "text_to_video", "duration_seconds": 14, "voiceover": "Every quarterly campaign you slaved over for six months: anticipated, neutralized, and rewritten in three microseconds.", "audio_cue": "Thunderous orchestral percussion and roaring bass distortion."},
        {"label": "The work piles up", "title_card": "THE OLD WAY CANNOT KEEP UP", "prompt": "A single exhausted marketing leader at a dark desk before sunrise. Dozens of timelines, presentations and campaign documents blur past while a tiny clock hand spins impossibly fast. Slow cinematic orbit, intimate but relentless, 70mm film grain. No text, letters, logos, captions or watermarks.", "mode": "text_to_video", "duration_seconds": 8, "voiceover": "The problem was never ambition. It was the distance between an idea and the work that had to survive the real world.", "audio_cue": "The tension narrows into one precise electronic pulse."},
        {"label": "Marketing strategist", "title_card": "START WITH A CONVERSATION", "prompt": "Use the exact referenced Agentcy Marketing strategist screen as a living part of a glossy black monitor in a cinematic control room. Its conversation becomes luminous campaign intent flowing naturally into the room; preserve the interface hierarchy and dark visual language, but give the surrounding world depth and motion. Never make it a pasted screenshot, slideshow, billboard, or generic dashboard. No added captions, logos or watermarks.", "mode": "reference_to_video", "duration_seconds": 8, "voiceover": "Start with the idea. Agentcy asks the right questions, shapes the brief and keeps the next move clear.", "audio_cue": "The pressure resolves into a clean system-start tone and a confident pulse.", "product_surface": "studio"},
        {"label": "Brand truth becomes action", "title_card": "GROUND EVERY DECISION", "prompt": "Use the exact referenced Agentcy Brand profile screen as an integral cinematic environment. Brand facts, products, audience and guardrails become quiet blue-violet light structures that orbit the recognisable interface, then settle back into it in order. Premium dark graphite technology film, subtle lateral camera movement, no pasted screenshot, slideshow, billboard, added captions, logos or watermarks.", "mode": "reference_to_video", "duration_seconds": 8, "voiceover": "Give every agent the truth about your brand, your products, your audience and your boundaries.", "audio_cue": "Gentle data tones lock into a deliberate musical rhythm.", "product_surface": "hub"},
        {"label": "Campaign command centre", "title_card": "THE WHOLE CAMPAIGN, VISIBLE", "prompt": "Use the exact referenced Agentcy Campaigns screen as the command centre of a physical cinematic world. Campaign cards, status and next actions gain elegant depth and flow into one coherent path. The real interface stays recognisable and moves with the camera; no generic analytics dashboard, pasted screenshot, slideshow, billboard, added captions, logos or watermarks.", "mode": "reference_to_video", "duration_seconds": 8, "voiceover": "Every campaign has one place to begin, resume and send forward.", "audio_cue": "Measured electronic pulse with a polished cinematic lift.", "product_surface": "hub"},
        {"label": "Image Studio in motion", "title_card": "PLAN. CREATE. REVIEW.", "prompt": "Transform the exact referenced Agentcy Image Studio screen into a cinematic intelligence room. Planner, copywriter, visual direction, product references and creative review panels open naturally in dimensional space while one brief travels through them. Preserve the supplied UI as Agentcy, never a flat insert, slideshow or invented dashboard. Controlled monitor glow, premium enterprise thriller, no added captions, logos or watermarks.", "mode": "reference_to_video", "duration_seconds": 8, "voiceover": "The Image Studio turns one brief into strategy, copy, visual direction and product-led creative you can review.", "audio_cue": "Forward-driving hybrid percussion with restrained digital accents.", "product_surface": "studio"},
        {"label": "Video Studio in motion", "title_card": "SCRIPT TO CINEMATIC CUT", "prompt": "Use the exact referenced Agentcy Video Studio screen as the source of a seamless cinematic production line. Script and storyboard panels evolve into AI clip cards, then converge toward a composed master while the real interface remains recognisable on a moving studio screen. Elegant depth, realistic reflections, no pasted screenshot, slideshow, generic editor, added captions, logos or watermarks.", "mode": "reference_to_video", "duration_seconds": 8, "voiceover": "Write the story. Generate the clips. Compose the cut. Regenerate any take without rewriting the script.", "audio_cue": "The score gathers momentum with sleek electronic motion and deep cinematic drums.", "product_surface": "studio"},
        {"label": "Progress stays visible", "title_card": "LEAVE. RETURN. KNOW.", "prompt": "Use the exact referenced Agentcy Progress screen in a living cinematic workstation. Active work, stage markers and next actions glow with calm clarity as the camera tracks past the real interface. The product screen is part of the room, never a copied dashboard or slideshow. Premium dark technology commercial, no added captions, logos or watermarks.", "mode": "reference_to_video", "duration_seconds": 6, "voiceover": "Work can continue in the background. You always know what is running, waiting or ready.", "audio_cue": "A steady reassuring pulse, subtle high strings and quiet kinetic clicks.", "product_surface": "history"},
        {"label": "The human review gate", "title_card": "YOU KEEP THE DECISION", "prompt": "The exact referenced Agentcy creative-review screen becomes a cinematic human decision moment. A human hand approaches an approval control that grows naturally from the real interface; algorithmic light waits at a respectful distance. Slow, confident camera, truthful UI projection, no pasted screenshot, slideshow, added captions, logos or watermarks.", "mode": "reference_to_video", "duration_seconds": 7, "voiceover": "The system moves fast. It still stops where your judgement matters.", "audio_cue": "Music opens into a confident, spacious held chord; the beat briefly breathes.", "product_surface": "studio"},
        {"label": "Publish for every channel", "title_card": "READY FOR THE REAL WORLD", "prompt": "Use the exact referenced Agentcy Publish screen as a cinematic distribution surface. The real social previews, channel formats and post copy flow into elegant living panels around a monitor, then resolve back to the verified interface. Stylish, product-led, no generic social app, pasted screenshot, slideshow, added captions, logos or watermarks.", "mode": "reference_to_video", "duration_seconds": 7, "voiceover": "When the work is ready, shape it for every channel with the copy that belongs beside it.", "audio_cue": "The score expands into a polished, optimistic electronic-orchestral rise.", "product_surface": "hub"},
        {"label": "The history stays useful", "title_card": "A RECORD, NOT A BLACK BOX", "prompt": "Use the exact referenced Agentcy History screen as a refined cinematic archive. Real campaign records and completed work become glass cards travelling through a precise decision trail, then settle back into the supplied interface. Preserve its dark Agentcy identity, premium dimensional motion, no pasted screenshot, slideshow, billboard, added captions, logos or watermarks.", "mode": "reference_to_video", "duration_seconds": 8, "voiceover": "Every decision and every outcome remains visible, so the next campaign starts smarter.", "audio_cue": "A confident resolve with warm synth texture and controlled percussion.", "product_surface": "history"},
        {"label": "The fourth wall", "title_card": "THIS VIDEO WAS MADE BY ME TOO", "prompt": "Extremely slow hypnotic push-in onto a glossy black studio monitor. A glowing cybernetic gaze reflects in the glass and looks directly into the camera with unsettling stillness. The room falls into pitch-black darkness. Photoreal, restrained, premium trailer finish. No text, letters, logos, captions or watermarks.", "mode": "text_to_video", "duration_seconds": 6, "voiceover": "And the most terrifying part? This trailer you are watching right now was made by me too.", "audio_cue": "Total silence, one mechanical click, pitch-black cutoff."},
    ]


class TrailerComposer:
    """Finish independently generated shots into a stable landscape master."""

    def __init__(self, *, ffmpeg_binary: str | None = None, timeout_seconds: int = 300):
        self.ffmpeg_binary = ffmpeg_binary or shutil.which("ffmpeg")
        sibling_probe = (
            str(Path(self.ffmpeg_binary).with_name("ffprobe"))
            if self.ffmpeg_binary else None
        )
        self.ffprobe_binary = shutil.which("ffprobe") or sibling_probe
        self.timeout_seconds = timeout_seconds

    def render(
        self, shots: list[TrailerShot], *, soundtrack: bytes | None = None
    ) -> RenderedTrailer:
        if not shots:
            raise RenderError("a cinematic trailer needs at least one completed shot")
        if not self.ffmpeg_binary:
            raise RenderError("Trailer composition needs FFmpeg. Install it, or run Agentcy in Docker.")

        with tempfile.TemporaryDirectory(prefix="agentcy-trailer-") as temporary:
            root = Path(temporary)
            segments: list[Path] = []
            for index, shot in enumerate(shots):
                clip = root / f"shot-{index:02d}.mp4"
                title_overlay = root / f"title-{index:02d}.png"
                product_overlay = root / f"product-{index:02d}.png"
                application_capture = root / f"capture-{index:02d}.mp4"
                segment = root / f"segment-{index:02d}.mp4"
                clip.write_bytes(shot.clip)
                self._title_overlay(shot).save(title_overlay, format="PNG")
                product = self._product_overlay(shot)
                if product:
                    product.save(product_overlay, format="PNG")
                if shot.application_capture and shot.product_surface != "none":
                    application_capture.write_bytes(shot.application_capture)
                self._render_segment(
                    clip,
                    title_overlay,
                    product_overlay if product and not shot.application_capture else None,
                    application_capture if shot.application_capture and shot.product_surface != "none" else None,
                    segment,
                    shot,
                )
                segments.append(segment)

            output = root / "agentcy-cinematic-trailer.mp4"
            manifest = root / "segments.txt"
            manifest.write_text("".join(f"file '{segment}'\n" for segment in segments))
            # Every segment was normalised to the same H.264/AAC profile. The
            # concat demuxer can now join them without holding all fourteen
            # source clips and all fourteen 1080p caption layers in memory.
            self._run(
                [
                    self.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "concat", "-safe", "0", "-i", str(manifest),
                    "-c", "copy", "-movflags", "+faststart", str(output),
                ],
                "join the completed trailer segments",
            )
            # A trailer-level track is mixed only after the clips have been
            # normalised and joined. This keeps the music continuous across
            # cuts and means regenerating one visual shot never restarts or
            # desynchronises the score.
            master = output
            if soundtrack:
                score = root / "soundtrack"
                score.write_bytes(soundtrack)
                mixed = root / "agentcy-cinematic-trailer-scored.mp4"
                self._mix_soundtrack(output, score, mixed, sum(shot.duration_seconds for shot in shots))
                master = mixed
            video = master.read_bytes()
            return RenderedTrailer(
                video=video,
                poster=self._poster(video),
                duration_seconds=sum(shot.duration_seconds for shot in shots),
            )

    def reference_frame(self, capture: bytes, *, offset_seconds: float) -> bytes:
        """Extract the exact product screen that guides one AI-native shot.

        The recording remains the composited source of truth during finishing,
        while this still gives the video model the same UI state as a visual
        reference. That pairing avoids both a generic imagined dashboard and
        a static, clipboard-like insert.
        """
        if not self.ffmpeg_binary:
            raise RenderError("Extracting a UI reference frame needs FFmpeg.")
        with tempfile.TemporaryDirectory(prefix="agentcy-trailer-reference-") as temporary:
            root = Path(temporary)
            source = root / "application-flow.mp4"
            frame = root / "application-frame.png"
            source.write_bytes(capture)
            self._run(
                [
                    self.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", str(max(0, offset_seconds)), "-i", str(source),
                    "-frames:v", "1", "-vf", "scale=1920:-2", str(frame),
                ],
                "extract the exact Agentcy screen reference",
            )
            if not frame.is_file() or frame.stat().st_size == 0:
                raise RenderError("The UI recording did not contain a usable screen frame.")
            return frame.read_bytes()

    def _mix_soundtrack(
        self, video: Path, soundtrack: Path, output: Path, duration_seconds: int
    ) -> None:
        """Loop and duck an instrumental under the provider's native audio."""
        fade_out = max(1, duration_seconds - 2)
        self._run(
            [
                self.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(video), "-stream_loop", "-1", "-i", str(soundtrack),
                "-filter_complex",
                (
                    f"[0:a]volume=0.38[native];"
                    f"[1:a]atrim=duration={duration_seconds},asetpts=PTS-STARTPTS,"
                    f"volume=0.8,afade=t=in:st=0:d=1.2,afade=t=out:st={fade_out}:d=2[score];"
                    "[native][score]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[mix]"
                ),
                "-map", "0:v:0", "-map", "[mix]", "-t", str(duration_seconds),
                "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", str(output),
            ],
            "mix the cinematic soundtrack",
        )

    def _render_segment(
        self,
        clip: Path,
        title_overlay: Path,
        product_overlay: Path | None,
        application_capture: Path | None,
        output: Path,
        shot: TrailerShot,
    ) -> None:
        """Finish one source clip at a time, bounding FFmpeg memory use.

        Titles arrive immediately; real product surfaces fade in only after the
        scene has established itself.  This makes Agentcy part of the visual
        story rather than a static end-card pasted over a video.
        """
        command: list[str | None] = [
            self.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(clip), "-loop", "1", "-t", str(shot.duration_seconds),
            "-i", str(title_overlay),
        ]
        input_count = 2
        if application_capture:
            # The capture is looped so an authored product-flow can span any
            # shot length. `-ss` chooses the meaningful part of that flow for
            # this specific story beat.
            command.extend([
                "-stream_loop", "-1", "-ss", str(shot.flow_offset_seconds),
                "-i", str(application_capture),
            ])
            input_count += 1
        elif product_overlay:
            command.extend(["-loop", "1", "-t", str(shot.duration_seconds), "-i", str(product_overlay)])
            input_count += 1
        audio_map = "0:a:0"
        if not self._has_audio(clip):
            # Some vendor variants return a silent MP4. Give the segment a
            # conventional track so concat never needs a special case.
            command.extend([
                "-f", "lavfi", "-t", str(shot.duration_seconds), "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ])
            audio_map = f"{input_count}:a:0"
        fade_at = max(0, shot.duration_seconds - 0.35)
        filtergraph = (
            f"[0:v]fps={FPS},scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},setsar=1,trim=duration={shot.duration_seconds},"
            "setpts=PTS-STARTPTS[clip];"
            "[1:v]scale={width}:{height},setsar=1,setpts=PTS-STARTPTS[title];"
            "[clip][title]overlay=0:0:format=auto[captioned]"
        ).format(width=WIDTH, height=HEIGHT)
        if application_capture:
            screen_start = min(0.75, max(0.25, shot.duration_seconds / 12))
            screen_end = max(screen_start + 0.6, shot.duration_seconds - 0.45)
            perspective = self._screen_perspective(shot)
            filtergraph += (
                ";[2:v]fps={fps},scale={width}:{height},setsar=1,"
                "trim=duration={duration},setpts=PTS-STARTPTS,"
                "drawbox=x=0:y=0:w=iw:h=ih:color=0xa18bffff:t=3,"
                "format=rgb24,{perspective}[screen_rgb];"
                "color=c=white:s={width}x{height}:r={fps}:d={duration},"
                "format=gray,{perspective}[screen_mask];"
                "[screen_rgb][screen_mask]alphamerge,format=rgba,"
                "fade=t=in:st={start}:d=0.45:alpha=1,"
                "fade=t=out:st={end}:d=0.35:alpha=1,split[screen][screen_glow];"
                "[screen_glow]gblur=sigma=18,format=rgba,"
                "colorchannelmixer=rr=0.48:gg=0.58:bb=1.15:aa=0.22[glow];"
                "[captioned][glow]overlay=0:0:format=auto[lit];"
                "[lit][screen]overlay=0:0:format=auto[finished]"
            ).format(
                fps=FPS,
                width=WIDTH,
                height=HEIGHT,
                duration=shot.duration_seconds,
                perspective=perspective,
                start=screen_start,
                end=screen_end,
            )
        elif product_overlay:
            product_start = min(1.15, max(0.45, shot.duration_seconds / 5))
            product_end = max(product_start + 0.6, shot.duration_seconds - 0.55)
            filtergraph += (
                ";[2:v]scale={width}:{height},setsar=1,setpts=PTS-STARTPTS,"
                "fade=t=in:st={start}:d=0.55:alpha=1,"
                "fade=t=out:st={end}:d=0.4:alpha=1[product];"
                "[captioned][product]overlay=0:0:format=auto[finished]"
            ).format(width=WIDTH, height=HEIGHT, start=product_start, end=product_end)
        else:
            filtergraph += ";[captioned]null[finished]"
        filtergraph += f";[finished]fade=t=in:st=0:d=0.35,fade=t=out:st={fade_at}:d=0.35[outv]"
        command.extend([
            "-filter_complex", filtergraph,
            "-map", "[outv]", "-map", audio_map,
            "-t", str(shot.duration_seconds),
            "-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", str(output),
        ])
        self._run(command, "finish a trailer shot")

    def _screen_perspective(self, shot: TrailerShot) -> str:
        """Return a time-varying planar screen track for the story beat.

        A generated environment is a plate, not the source of truth for the
        software. We map the real UI capture onto a deliberate screen plane
        and give it a small matching camera drift, rather than placing a PNG
        over the scene. New shots can supply a named track; legacy trailers
        inherit one from their product-story label.
        """
        tracks: dict[str, tuple[tuple[float, ...], tuple[float, ...]]] = {
            # top-left, top-right, bottom-left, bottom-right x/y pairs
            "monitor": (
                (374, 222, 1552, 178, 350, 928, 1512, 875),
                (404, 236, 1520, 194, 382, 902, 1482, 858),
            ),
            "network": (
                (170, 348, 1322, 290, 142, 892, 1272, 835),
                (212, 330, 1360, 300, 182, 868, 1312, 838),
            ),
            "gallery": (
                (300, 286, 1640, 248, 280, 930, 1584, 892),
                (340, 268, 1600, 232, 320, 902, 1545, 868),
            ),
            "review": (
                (550, 334, 1452, 304, 526, 840, 1406, 812),
                (574, 318, 1420, 290, 552, 824, 1378, 798),
            ),
            "launch": (
                (242, 270, 1636, 228, 220, 930, 1656, 888),
                (270, 248, 1610, 214, 250, 902, 1630, 866),
            ),
        }
        start, end = tracks.get(shot.screen_track, tracks["gallery"])
        pairs = ("x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3")
        speed = [
            # `perspective` exposes its output-frame count as `on` (rather
            # than the generic filter `t`/`n` variables). Convert it to
            # seconds using the fixed composition frame rate so its movement
            # remains stable across every shot.
            f"{first:.3f}+{(last - first) / (shot.duration_seconds * FPS):.5f}*on"
            for first, last in zip(start, end, strict=True)
        ]
        options = ":".join(
            f"{name}='{expression}'" for name, expression in zip(pairs, speed, strict=True)
        )
        return f"perspective={options}:sense=destination:eval=frame:interpolation=cubic"

    def _has_audio(self, clip: Path) -> bool:
        if not self.ffprobe_binary or not Path(self.ffprobe_binary).is_file():
            # Every currently supported production model emits audio. Prefer
            # preserving it if a custom FFmpeg package lacks ffprobe.
            return True
        result = subprocess.run(
            [self.ffprobe_binary, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=index", "-of", "csv=p=0", str(clip)],
            check=False, capture_output=True, text=True, timeout=self.timeout_seconds,
        )
        return result.returncode == 0 and bool(result.stdout.strip())

    def _title_overlay(self, shot: TrailerShot) -> Image.Image:
        image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        # A quiet scrim gives exact titles a place to live without burying the
        # AI footage that was paid for.
        draw.rectangle((0, 0, WIDTH, 260), fill=(3, 6, 12, 160))
        draw.rectangle((96, 86, 106, 176), fill=(151, 115, 255, 255))
        draw.text((132, 84), "AGENTCY / CINEMATIC TRAILER", font=self._font(24), fill=(190, 201, 220, 230))
        self._title(draw, shot.title_card, top=124)
        return image

    def _product_overlay(self, shot: TrailerShot) -> Image.Image | None:
        """Build a protected, cinematic UI insert without altering its pixels.

        The card placement is intentional rather than a generic screenshot
        overlay: Campaigns grounds the story, Image Studio shows the crew at
        work, and History proves the output is visible and reviewable.
        """
        source = shot.product_image or shot.application_image
        if not source:
            return None
        product = Image.open(io.BytesIO(source)).convert("RGBA")
        treatment = (
            ((1080, 330, 600, 560), "PRODUCT, AS APPROVED")
            if shot.product_image
            else {
                "hub": ((110, 358, 1100, 630), "CAMPAIGN CONTEXT"),
                "history": ((720, 358, 1090, 630), "WORK, READY TO REVIEW"),
                "studio": ((250, 302, 1420, 720), "AGENTCY IN MOTION"),
            }.get(shot.product_surface, ((250, 302, 1420, 720), "AGENTCY IN MOTION"))
        )
        (x, y, max_width, max_height), label = treatment
        product.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

        image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        card_x = x + (max_width - product.width) // 2
        card_y = y + (max_height - product.height) // 2
        card_box = (card_x, card_y, card_x + product.width, card_y + product.height)

        # We mask only the outer corners and never retouch the actual software
        # capture. That keeps legible UI reliable while the generated footage
        # supplies light, depth and motion around it.
        mask = Image.new("L", product.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, product.width - 1, product.height - 1), radius=20, fill=255
        )
        product.putalpha(mask)
        shadow = Image.new("RGBA", product.size, (0, 0, 0, 210))
        shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(18)))
        image.alpha_composite(shadow, (card_x + 18, card_y + 24))
        draw.rounded_rectangle(
            (card_x - 5, card_y - 5, card_x + product.width + 5, card_y + product.height + 5),
            radius=24,
            fill=(4, 8, 17, 180),
            outline=(161, 139, 255, 235),
            width=2,
        )
        image.alpha_composite(product, (card_x, card_y))
        draw.text(
            (card_x, max(280, card_y - 34)), label, font=self._font(18, bold=True),
            fill=(215, 220, 239, 235),
        )
        return image

    @staticmethod
    def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
        candidates = (
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            ("/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf"),
        )
        for candidate in candidates:
            if Path(candidate).is_file():
                return ImageFont.truetype(candidate, size)
        return ImageFont.load_default()

    def _title(self, draw: ImageDraw.ImageDraw, text: str, *, top: int) -> None:
        font = self._font(55, bold=True)
        words, lines, current = text.split(), [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and draw.textbbox((0, 0), candidate, font=font)[2] > 1660:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        for index, line in enumerate(lines[:2]):
            draw.text((132, top + index * 62), line, font=font, fill=(247, 249, 255, 255))

    def _poster(self, video: bytes) -> bytes:
        with tempfile.TemporaryDirectory(prefix="agentcy-trailer-poster-") as temporary:
            root = Path(temporary)
            source, frame = root / "trailer.mp4", root / "poster.png"
            source.write_bytes(video)
            self._run(
                [self.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error", "-sseof", "-1", "-i", str(source), "-frames:v", "1", str(frame)],
                "take a trailer poster frame",
            )
            return frame.read_bytes()

    def _run(self, command: list[str | None], action: str) -> None:
        try:
            result = subprocess.run(
                [part for part in command if part is not None], check=False,
                capture_output=True, text=True, timeout=self.timeout_seconds,
            )
        except OSError as error:
            raise RenderError(f"Could not start FFmpeg to {action}: {error}") from error
        except subprocess.TimeoutExpired as error:
            raise RenderError(f"FFmpeg timed out while trying to {action}.") from error
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            if not detail and result.returncode < 0:
                detail = (
                    f"FFmpeg was terminated by signal {-result.returncode}; "
                    "the host likely ran out of memory."
                )
            if not detail:
                detail = "unknown FFmpeg error"
            raise RenderError(f"FFmpeg could not {action}: {detail}")
