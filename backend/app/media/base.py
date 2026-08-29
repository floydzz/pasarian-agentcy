"""Provider-neutral image and video rendering.

Mirrors `app.llm.base` on purpose: one abstract class, one registry, one
offline provider, so swapping the vendor is an environment change rather than
an edit to any agent. The plan's risk register calls the media vendor landscape
unreliable, and this is the seam that makes that survivable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

#: Longest a single render may take before it is abandoned. A demo must never
#: hang on a vendor — the same rule the crew follows for agents.
DEFAULT_TIMEOUT_SECONDS = 120

#: Frame shapes the pipeline renders. A channel convention, not a model choice.
ASPECTS: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "9:16": (720, 1280),
    "16:9": (1280, 720),
}


class RenderError(RuntimeError):
    """A media provider could not produce a usable asset."""


class MediaProvider(ABC):
    """One prompt in, image bytes out."""

    #: Providers reached over HTTP override this with their API root.
    base_url: str | None = None

    def __init__(
        self,
        *,
        api_key: str,
        image_model: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not api_key:
            raise ValueError(
                f"{type(self).__name__} needs an API key — set the matching "
                "key in .env before rendering"
            )
        self.api_key = api_key
        self.image_model = image_model or self.default_image_model
        self.timeout_seconds = timeout_seconds

    @property
    @abstractmethod
    def default_image_model(self) -> str: ...

    @abstractmethod
    def render_image(
        self,
        prompt: str,
        *,
        aspect: str = "1:1",
        reference_images: tuple[bytes, ...] = (),
    ) -> bytes:
        """PNG or JPEG bytes for `prompt`. Raises `RenderError` on failure.

        `reference_images` are photographs the render must build around rather
        than reinvent — a marketer's product lock. A provider given them makes
        an edit-style call, so the real product is lit and placed by the model
        instead of being pasted over the finished frame.
        """

    @staticmethod
    def size_for(aspect: str) -> tuple[int, int]:
        try:
            return ASPECTS[aspect]
        except KeyError:
            raise RenderError(
                f"unsupported aspect {aspect!r} — supported: "
                f"{', '.join(sorted(ASPECTS))}"
            ) from None
