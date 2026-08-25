"""Compositing real typography onto a generated background.

The chosen vendor is weakest exactly where the plan is strictest — legible text
in the frame (`plan:40`). So the model is never asked to draw words. It renders
a background with deliberate negative space, and the headline and CTA are drawn
here as real type at the zone the visual planner picked.

Text colour is not something an agent decides. Asking a planner to predict the
brightness of an image that does not exist yet is a guess; the rendered pixels
are ground truth, so contrast is sampled from them.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageStat

from app.config import REPO_ROOT

from .base import MediaProvider

#: The nine-cell grid as fractions of the frame: (left, top, right, bottom).
ZONES: dict[str, tuple[float, float, float, float]] = {
    "top-left": (0.06, 0.06, 0.60, 0.34),
    "top-center": (0.12, 0.06, 0.88, 0.34),
    "top-right": (0.40, 0.06, 0.94, 0.34),
    "mid-left": (0.06, 0.36, 0.60, 0.64),
    "mid-center": (0.12, 0.36, 0.88, 0.64),
    "mid-right": (0.40, 0.36, 0.94, 0.64),
    "bottom-left": (0.06, 0.66, 0.60, 0.94),
    "bottom-center": (0.12, 0.66, 0.88, 0.94),
    "bottom-right": (0.40, 0.66, 0.94, 0.94),
}

#: Preferred faces, in order. The container installs fonts-dejavu-core.
FONT_DIR = REPO_ROOT / "backend" / "data" / "fonts"
SYSTEM_FONTS = {
    True: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ],
    False: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ],
}

LIGHT_TEXT = (255, 255, 255)
DARK_TEXT = (17, 17, 17)

#: Above this mean luminance the background counts as light.
LUMINANCE_PIVOT = 140


def resolve_font(size: int, *, bold: bool) -> ImageFont.ImageFont:
    """A drawable face at `size`, whatever the host happens to have.

    Falls through to Pillow's built-in so a native test run on a machine with
    no DejaVu still composes rather than raising.
    """
    if FONT_DIR.is_dir():
        wanted = "bold" if bold else "regular"
        for candidate in sorted(FONT_DIR.glob("*.ttf")):
            if wanted in candidate.name.lower():
                return ImageFont.truetype(candidate, size=size)

    for path in SYSTEM_FONTS[bold]:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)

    return ImageFont.load_default(size=size)


def pick_text_colour(region: Image.Image) -> tuple[int, int, int]:
    """Light type on a dark region, dark type on a light one."""
    mean = ImageStat.Stat(region.convert("L")).mean[0]
    return DARK_TEXT if mean > LUMINANCE_PIVOT else LIGHT_TEXT


def compose_creative(
    background: bytes,
    *,
    headline: str,
    cta: str,
    zone: str,
    aspect: str = "1:1",
) -> bytes:
    if zone not in ZONES:
        raise ValueError(
            f"unknown placement zone {zone!r} — expected one of "
            f"{', '.join(sorted(ZONES))}"
        )

    width, height = MediaProvider.size_for(aspect)
    image = Image.open(io.BytesIO(background)).convert("RGB")
    if image.size != (width, height):
        # Cover, then centre-crop: letterboxing an ad would be worse.
        image = _cover(image, width, height)

    left, top, right, bottom = ZONES[zone]
    box = (
        int(left * width),
        int(top * height),
        int(right * width),
        int(bottom * height),
    )
    colour = pick_text_colour(image.crop(box))

    # A scrim under the type, so a busy background cannot beat the contrast we
    # just measured. Drawn on its own layer to keep it translucent.
    scrim = Image.new("RGBA", image.size, (0, 0, 0, 0))
    scrim_colour = (0, 0, 0, 90) if colour == LIGHT_TEXT else (255, 255, 255, 110)
    ImageDraw.Draw(scrim).rounded_rectangle(_pad(box, 18, width, height), 24, fill=scrim_colour)
    image = Image.alpha_composite(image.convert("RGBA"), scrim).convert("RGB")

    draw = ImageDraw.Draw(image)
    box_width = box[2] - box[0]
    box_height = box[3] - box[1]

    headline_font, lines = _fit(draw, headline, box_width, int(box_height * 0.66), bold=True)
    cta_font = resolve_font(max(headline_font.size // 2, 14), bold=False)

    y = box[1]
    for line in lines:
        draw.text((box[0], y), line, font=headline_font, fill=colour)
        y += _line_height(draw, line, headline_font)

    draw.text((box[0], y + 12), cta.upper(), font=cta_font, fill=colour)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# -- helpers ---------------------------------------------------------------


def _cover(image: Image.Image, width: int, height: int) -> Image.Image:
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (max(round(image.width * scale), width), max(round(image.height * scale), height)),
        Image.Resampling.LANCZOS,
    )
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _pad(box: tuple[int, int, int, int], amount: int, width: int, height: int):
    return (
        max(box[0] - amount, 0),
        max(box[1] - amount, 0),
        min(box[2] + amount, width),
        min(box[3] + amount, height),
    )


def _line_height(draw: ImageDraw.ImageDraw, line: str, font) -> int:
    top, bottom = draw.textbbox((0, 0), line or "X", font=font)[1::2]
    return int((bottom - top) * 1.35)


def _fit(draw, text: str, box_width: int, box_height: int, *, bold: bool):
    """Largest size at which `text` wraps inside the box. Never returns nothing.

    Steps down rather than solving for it: the search is a dozen iterations on
    an image that took seconds to generate, and stepping is easy to read.
    """
    size = max(box_width // 8, 16)
    while size > 12:
        font = resolve_font(size, bold=bold)
        lines = _wrap(draw, text, font, box_width)
        if sum(_line_height(draw, line, font) for line in lines) <= box_height:
            return font, lines
        size -= 4

    font = resolve_font(12, bold=bold)
    return font, _wrap(draw, text, font, box_width)


def _wrap(draw, text: str, font, box_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= box_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
