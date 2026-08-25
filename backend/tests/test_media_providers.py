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


from app.media.dashscope import DashScopeMediaProvider

IMAGE_BYTES = b"\x89PNG\r\n\x1a\nfake-but-sufficient"


def _provider(handler, **kwargs):
    provider = DashScopeMediaProvider(api_key="sk-test", **kwargs)
    provider._client_factory = lambda: httpx.Client(
        transport=httpx.MockTransport(handler), base_url=provider.base_url
    )
    return provider


def test_submits_polls_and_downloads():
    seen = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/image-synthesis"):
            assert request.headers["X-DashScope-Async"] == "enable"
            assert request.headers["Authorization"] == "Bearer sk-test"
            return httpx.Response(200, json={"output": {"task_id": "t-1"}})
        if "/tasks/" in request.url.path:
            seen["polls"] += 1
            if seen["polls"] < 2:
                return httpx.Response(200, json={"output": {"task_status": "RUNNING"}})
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_status": "SUCCEEDED",
                        "results": [{"url": "https://cdn.example/out.png"}],
                    }
                },
            )
        return httpx.Response(200, content=IMAGE_BYTES)

    provider = _provider(handler, poll_interval_seconds=0)
    assert provider.render_image("a warung at golden hour") == IMAGE_BYTES
    assert seen["polls"] == 2


def test_sends_the_size_matching_the_aspect():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/image-synthesis"):
            captured.update(json.loads(request.content))
            return httpx.Response(200, json={"output": {"task_id": "t-1"}})
        if "/tasks/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_status": "SUCCEEDED",
                        "results": [{"url": "https://cdn.example/out.png"}],
                    }
                },
            )
        return httpx.Response(200, content=IMAGE_BYTES)

    provider = _provider(handler, poll_interval_seconds=0)
    provider.render_image("x", aspect="9:16")
    assert captured["parameters"]["size"] == "720*1280"


def test_failed_task_raises_render_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/image-synthesis"):
            return httpx.Response(200, json={"output": {"task_id": "t-1"}})
        return httpx.Response(
            200,
            json={"output": {"task_status": "FAILED", "message": "content rejected"}},
        )

    provider = _provider(handler, poll_interval_seconds=0)
    with pytest.raises(RenderError, match="content rejected"):
        provider.render_image("x")


def test_timeout_raises_render_error_rather_than_polling_forever():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/image-synthesis"):
            return httpx.Response(200, json={"output": {"task_id": "t-1"}})
        return httpx.Response(200, json={"output": {"task_status": "RUNNING"}})

    provider = _provider(handler, poll_interval_seconds=0, timeout_seconds=0)
    with pytest.raises(RenderError, match="did not finish"):
        provider.render_image("x")


def test_http_error_on_submit_raises_render_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid key"})

    provider = _provider(handler, poll_interval_seconds=0)
    with pytest.raises(RenderError):
        provider.render_image("x")


def test_dashscope_demands_a_key():
    with pytest.raises(ValueError, match="needs an API key"):
        DashScopeMediaProvider(api_key="")
