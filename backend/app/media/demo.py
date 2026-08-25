"""An offline image provider for rehearsing the pipeline. Not a model.

Renders a deterministic placeholder from the prompt's own hash, so a rehearsal
looks the same every time it is run and two different briefs never produce the
same picture. Every frame says `[demo]` on it: nothing this returns should ever
reach a deck by accident.
"""

from __future__ import annotations

import hashlib
import io

from PIL import Image, ImageDraw

from .base import MediaProvider


class DemoMediaProvider(MediaProvider):
    def __init__(
        self,
        *,
        api_key: str = "demo",
        image_model: str | None = None,
        timeout_seconds: int = 5,
    ) -> None:
        # Deliberately not calling super(): this provider has no key to demand.
        self.api_key = api_key
        self.image_model = image_model or self.default_image_model
        self.timeout_seconds = timeout_seconds

    @property
    def default_image_model(self) -> str:
        return "demo-offline"

    def render_image(self, prompt: str, *, aspect: str = "1:1") -> bytes:
        width, height = self.size_for(aspect)
        digest = hashlib.sha256(prompt.encode("utf-8")).digest()

        # Two hues from the digest, so the gradient is stable per prompt.
        top = (digest[0], digest[1], digest[2])
        bottom = (digest[3], digest[4], digest[5])

        image = Image.new("RGB", (width, height), top)
        draw = ImageDraw.Draw(image)
        for y in range(height):
            blend = y / max(height - 1, 1)
            draw.line(
                [(0, y), (width, y)],
                fill=tuple(
                    round(top[channel] + (bottom[channel] - top[channel]) * blend)
                    for channel in range(3)
                ),
            )

        draw.text((24, 24), "[demo]", fill=(255, 255, 255))

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
