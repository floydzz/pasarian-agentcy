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


from app.config import Settings
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
        if request.url.path.endswith("/generation"):
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
                        "choices": [
                            {"message": {"content": [
                                {"image": "https://cdn.example/out.png"}
                            ]}}
                        ],
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
        if request.url.path.endswith("/generation"):
            captured.update(json.loads(request.content))
            return httpx.Response(200, json={"output": {"task_id": "t-1"}})
        if "/tasks/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_status": "SUCCEEDED",
                        "choices": [
                            {"message": {"content": [
                                {"image": "https://cdn.example/out.png"}
                            ]}}
                        ],
                    }
                },
            )
        return httpx.Response(200, content=IMAGE_BYTES)

    provider = _provider(handler, poll_interval_seconds=0)
    provider.render_image("x", aspect="9:16")
    assert captured["parameters"]["size"] == "720*1280"


def test_failed_task_raises_render_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
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
        if request.url.path.endswith("/generation"):
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


def test_prompt_is_sent_in_the_messages_shape_the_wan_models_require():
    """The wan2.x models replaced `input.prompt` with `input.messages`;
    the old flat field is silently ignored. Verified live 2026-08-26."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            captured.update(json.loads(request.content))
            return httpx.Response(200, json={"output": {"task_id": "t-1"}})
        if "/tasks/" in request.url.path:
            return httpx.Response(200, json={"output": {
                "task_status": "SUCCEEDED",
                "choices": [{"message": {"content": [{"image": "https://cdn.example/o.png"}]}}],
            }})
        return httpx.Response(200, content=IMAGE_BYTES)

    provider = _provider(handler, poll_interval_seconds=0)
    provider.render_image("a warung at golden hour")
    assert captured["input"]["messages"] == [
        {"role": "user", "content": [{"text": "a warung at golden hour"}]}
    ]
    assert "prompt" not in captured["input"]


def test_submits_to_the_image_generation_endpoint():
    assert "image-generation/generation" in __import__(
        "app.media.dashscope", fromlist=["SUBMIT_PATH"]
    ).SUBMIT_PATH


def test_a_success_with_no_image_in_it_is_an_error_not_an_empty_render():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            return httpx.Response(200, json={"output": {"task_id": "t-1"}})
        return httpx.Response(200, json={"output": {
            "task_status": "SUCCEEDED", "choices": [{"message": {"content": []}}]}})

    provider = _provider(handler, poll_interval_seconds=0)
    with pytest.raises(RenderError, match="no image"):
        provider.render_image("x")


class TestTheWan26RequestShape:
    """`wan2.6-image` needs one parameter its predecessor did not.

    Probed against the live API on 2026-08-27, text-to-image with no input
    image attached:

        {"size": ..., "n": 1}                        -> task FAILED
            "When 'enable_interleave' is False, the last message must
             contain 1 to 4 images. Got 0 images."
        {"size": ..., "n": 1, "enable_interleave": True}  -> SUCCEEDED

    With it off the model reads the call as an *edit* and demands something to
    edit. Every prompt this pipeline sends is text-only, so the flag is always
    on. It is sent for every wan model rather than switched on the name:
    `wan2.7-image` takes the same endpoint and the same envelope, and a
    parameter it does not read is cheaper than a special case that goes stale.
    """

    def _submitted(self, model="wan2.6-image"):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if "generation" in request.url.path:
                captured.update(json.loads(request.content))
                return httpx.Response(200, json={"output": {"task_id": "t-1"}})
            if "/tasks/" in request.url.path:
                return httpx.Response(200, json={"output": {
                    "task_status": "SUCCEEDED",
                    "choices": [{"message": {"content": [
                        {"image": "https://cdn.example/out.png"}]}}],
                }})
            return httpx.Response(200, content=b"PNG")

        provider = DashScopeMediaProvider(
            api_key="sk-test", image_model=model, poll_interval_seconds=0
        )
        provider._client_factory = lambda: httpx.Client(
            transport=httpx.MockTransport(handler), base_url=provider.base_url
        )
        provider.render_image("a tidy desk")
        return captured

    def test_interleaving_is_turned_on(self):
        assert self._submitted()["parameters"]["enable_interleave"] is True

    def test_the_older_model_gets_it_too(self):
        assert self._submitted("wan2.7-image")["parameters"]["enable_interleave"] is True

    def test_the_prompt_still_travels_as_a_message(self):
        content = self._submitted()["input"]["messages"][0]["content"]
        assert content == [{"text": "a tidy desk"}]


class TestTheDefaultImageModelHasQuota:
    def test_it_is_the_wan_model_that_still_answers(self):
        """`wan2.7-image` returned 403 AllocationQuota.FreeTierOnly on
        2026-08-27; `wan2.6-image` rendered on the same key and account."""
        assert DashScopeMediaProvider(api_key="k").default_image_model == "wan2.6-image"


class TestTheTimeoutClearsTheModel:
    def test_it_allows_for_how_slow_wan26_actually_is(self):
        """One 1024x1024 render measured 166.0s end to end on 2026-08-27
        (submit 11:25:12, end 11:27:57). The previous 120s would have timed
        out every creative in the campaign, and 180s left fourteen seconds of
        headroom on a vendor that queues.

        Asserted on the declared default rather than on `get_settings()`:
        `.env` is not in the repository, so reading the ambient value here
        would make the suite pass or fail on a file nobody can review.
        """
        default = Settings.model_fields["media_timeout_seconds"].default
        assert default >= 300


def _succeeding_handler(captured: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            captured.update(json.loads(request.content))
            return httpx.Response(200, json={"output": {"task_id": "t-1"}})
        if "/tasks/" in request.url.path:
            return httpx.Response(200, json={"output": {
                "task_status": "SUCCEEDED",
                "choices": [{"message": {"content": [{"image": "https://cdn.example/o.png"}]}}],
            }})
        return httpx.Response(200, content=IMAGE_BYTES)

    return handler


def test_a_reference_image_is_sent_to_the_model_as_an_edit_input():
    """Product lock means the photo goes *into* the generation, not on top of
    it afterwards. wan2.6 reads a message carrying images as an edit."""
    captured: dict = {}
    provider = _provider(_succeeding_handler(captured), poll_interval_seconds=0)
    provider.render_image("a warung at golden hour", reference_images=(IMAGE_BYTES,))

    content = captured["input"]["messages"][0]["content"]
    assert content[-1] == {"text": "a warung at golden hour"}
    images = [part["image"] for part in content if "image" in part]
    assert len(images) == 1
    assert images[0].startswith("data:image/png;base64,")
    # `enable_interleave` is what marks a call as a fresh generation. An edit
    # must not carry it, or the reference images are ignored.
    assert "enable_interleave" not in captured["parameters"]


def test_a_render_without_references_stays_a_plain_generation():
    captured: dict = {}
    provider = _provider(_succeeding_handler(captured), poll_interval_seconds=0)
    provider.render_image("a warung at golden hour")

    assert captured["input"]["messages"][0]["content"] == [{"text": "a warung at golden hour"}]
    assert captured["parameters"]["enable_interleave"] is True


def test_more_than_four_reference_images_is_refused_before_the_call():
    provider = _provider(_succeeding_handler({}), poll_interval_seconds=0)
    with pytest.raises(RenderError, match="1 to 4"):
        provider.render_image("x", reference_images=(IMAGE_BYTES,) * 5)


def test_demo_provider_accepts_reference_images():
    provider = DemoMediaProvider()
    assert provider.render_image("x", reference_images=(IMAGE_BYTES,))
