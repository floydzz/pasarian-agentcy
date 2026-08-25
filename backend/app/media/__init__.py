"""Media provider registry — swap vendors without touching the studio."""

from __future__ import annotations

from .base import ASPECTS, MediaProvider, RenderError
from .dashscope import DashScopeMediaProvider
from .demo import DemoMediaProvider

MEDIA_PROVIDERS: dict[str, type[MediaProvider]] = {
    "dashscope": DashScopeMediaProvider,
    # Offline rehearsal — see app/media/demo.py. Not a model.
    "demo": DemoMediaProvider,
}


def get_media_provider(
    name: str,
    *,
    api_key: str,
    image_model: str | None = None,
    timeout_seconds: int = 120,
) -> MediaProvider:
    try:
        provider_cls = MEDIA_PROVIDERS[name.strip().lower()]
    except KeyError:
        raise ValueError(
            f"unknown media provider {name!r} — supported: "
            f"{', '.join(sorted(MEDIA_PROVIDERS))}"
        ) from None
    return provider_cls(
        api_key=api_key, image_model=image_model, timeout_seconds=timeout_seconds
    )


__all__ = [
    "ASPECTS",
    "MediaProvider",
    "RenderError",
    "DashScopeMediaProvider",
    "DemoMediaProvider",
    "MEDIA_PROVIDERS",
    "get_media_provider",
]
