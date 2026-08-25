import io
import json

import httpx
import pytest
from PIL import Image

from app.media import MEDIA_PROVIDERS, get_media_provider
from app.media.base import MediaProvider, RenderError
from app.media.demo import DemoMediaProvider


def test_demo_provider_returns_a_decodable_png():
    provider = DemoMediaProvider()
    data = provider.render_image("a warung at golden hour")
    image = Image.open(io.BytesIO(data))
    assert image.format == "PNG"
    assert image.size == (1024, 1024)


def test_demo_provider_is_deterministic_for_the_same_prompt():
    provider = DemoMediaProvider()
    assert provider.render_image("same") == provider.render_image("same")


def test_demo_provider_differs_across_prompts():
    provider = DemoMediaProvider()
    assert provider.render_image("one") != provider.render_image("two")


def test_demo_provider_honours_aspect():
    provider = DemoMediaProvider()
    assert Image.open(io.BytesIO(provider.render_image("x", aspect="9:16"))).size == (720, 1280)


def test_demo_provider_needs_no_key():
    assert DemoMediaProvider().api_key == "demo"


def test_registry_resolves_demo():
    assert isinstance(get_media_provider("demo", api_key="demo"), DemoMediaProvider)


def test_registry_names_the_supported_providers_when_asked_for_a_bad_one():
    with pytest.raises(ValueError, match="unknown media provider"):
        get_media_provider("midjourney", api_key="x")


def test_registry_covers_every_declared_provider():
    for name in MEDIA_PROVIDERS:
        assert issubclass(MEDIA_PROVIDERS[name], MediaProvider)


def test_render_error_is_a_runtime_error():
    assert issubclass(RenderError, RuntimeError)
