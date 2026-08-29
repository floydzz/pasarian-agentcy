"""The generative b-roll provider.

Every shape asserted here was verified against the live DashScope API on
2026-08-26; the notes say which behaviours are the vendor's and not ours.
"""

import json

import httpx
import pytest

from app.media.base import RenderError
from app.video.broll import (
    VIDEO_PROVIDERS,
    BrollProvider,
    CachingBrollProvider,
    DashScopeVideoProvider,
    DemoVideoProvider,
    VideoGenerationRequest,
    get_video_provider,
)

MP4 = b"\x00\x00\x00\x18ftypmp42fake"


def _provider(handler, **kwargs):
    provider = DashScopeVideoProvider(api_key="sk-test", **kwargs)
    provider._client_factory = lambda: httpx.Client(
        transport=httpx.MockTransport(handler), base_url=provider.base_url
    )
    return provider


def _ok_task(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/video-synthesis"):
        return httpx.Response(200, json={"output": {"task_id": "t-1"}})
    if "/tasks/" in request.url.path:
        return httpx.Response(
            200,
            json={
                "output": {
                    "task_status": "SUCCEEDED",
                    "video_url": "https://cdn.example/out.mp4",
                }
            },
        )
    return httpx.Response(200, content=MP4)


class TestRegistry:
    def test_resolves_the_offline_provider(self):
        assert isinstance(get_video_provider("demo", api_key="demo"), DemoVideoProvider)

    def test_resolves_dashscope(self):
        assert isinstance(
            get_video_provider("dashscope", api_key="k"), DashScopeVideoProvider
        )

    def test_unknown_provider_names_the_supported_ones(self):
        with pytest.raises(ValueError, match="unknown video provider"):
            get_video_provider("sora", api_key="x")

    def test_every_declared_provider_implements_the_contract(self):
        for name in VIDEO_PROVIDERS:
            assert issubclass(VIDEO_PROVIDERS[name], BrollProvider)


class TestRequestShape:
    def _captured(self, **kwargs):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/video-synthesis"):
                captured.update(json.loads(request.content))
            return _ok_task(request)

        _provider(handler, poll_interval_seconds=0).render_clip("a tidy desk", **kwargs)
        return captured

    def test_vertical_is_requested_with_ratio_not_size(self):
        """`size` and `aspect_ratio` are accepted and then silently ignored,
        yielding 16:9. Only `ratio` actually steers the output shape."""
        parameters = self._captured(aspect="9:16")["parameters"]
        assert parameters["ratio"] == "9:16"
        assert "size" not in parameters
        assert "aspect_ratio" not in parameters

    def test_the_watermark_is_turned_off(self):
        """happyhorse burns a "Happy Horse" mark bottom-right by default.
        `watermark: False` removes it; `add_watermark` is ignored."""
        assert self._captured()["parameters"]["watermark"] is False

    def test_duration_is_passed_through(self):
        assert self._captured(seconds=5)["parameters"]["duration"] == 5

    def test_the_prompt_travels_in_input(self):
        assert self._captured()["input"]["prompt"] == "a tidy desk"

    def test_it_submits_asynchronously(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/video-synthesis"):
                seen["async"] = request.headers.get("X-DashScope-Async")
            return _ok_task(request)

        _provider(handler, poll_interval_seconds=0).render_clip("x")
        assert seen["async"] == "enable"


class TestCinematicRequestShape:
    def test_an_image_to_video_shot_selects_the_matching_model_and_first_frame(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/video-synthesis"):
                captured.update(json.loads(request.content))
            return _ok_task(request)

        _provider(handler).submit_generation(
            VideoGenerationRequest(
                prompt="slow push into a monitor", mode="image_to_video",
                reference_images=(b"png-bytes",), seconds=8,
            )
        )

        assert captured["model"] == "happyhorse-1.1-i2v"
        assert captured["input"]["media"][0]["type"] == "first_frame"
        assert captured["input"]["media"][0]["url"].startswith("data:image/png;base64,")
        assert captured["parameters"]["resolution"] == "1080P"

    def test_reference_to_video_labels_each_input_as_a_reference_image(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/video-synthesis"):
                captured.update(json.loads(request.content))
            return _ok_task(request)

        _provider(handler).submit_generation(
            VideoGenerationRequest(
                prompt="[Image 1] and [Image 2] in one scene",
                mode="reference_to_video", reference_images=(b"first", b"second"),
            )
        )

        assert captured["model"] == "happyhorse-1.1-r2v"
        assert [item["type"] for item in captured["input"]["media"]] == [
            "reference_image", "reference_image"
        ]


class TestClamping:
    def test_a_clip_shorter_than_the_model_floor_is_raised_to_it(self):
        """happyhorse refuses anything under 3s; the storyboard's own scene
        length is 3s, so this only bites on a shortened scene."""

        def handler(request):
            return _ok_task(request)

        provider = _provider(handler, poll_interval_seconds=0)
        assert provider._duration(1) == 3

    def test_a_clip_longer_than_the_model_ceiling_is_capped(self):
        def handler(request):
            return _ok_task(request)

        provider = _provider(handler, poll_interval_seconds=0)
        assert provider._duration(60) == 15


class TestFailureModes:
    def test_it_returns_the_downloaded_bytes(self):
        assert _provider(_ok_task, poll_interval_seconds=0).render_clip("x") == MP4

    def test_a_failed_task_raises_render_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/video-synthesis"):
                return httpx.Response(200, json={"output": {"task_id": "t-1"}})
            return httpx.Response(
                200,
                json={"output": {"task_status": "FAILED", "message": "unsafe prompt"}},
            )

        with pytest.raises(RenderError, match="unsafe prompt"):
            _provider(handler, poll_interval_seconds=0).render_clip("x")

    def test_it_gives_up_rather_than_polling_forever(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/video-synthesis"):
                return httpx.Response(200, json={"output": {"task_id": "t-1"}})
            return httpx.Response(200, json={"output": {"task_status": "RUNNING"}})

        provider = _provider(handler, poll_interval_seconds=0, timeout_seconds=0)
        with pytest.raises(RenderError, match="did not finish"):
            provider.render_clip("x")

    def test_a_success_carrying_no_video_is_an_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/video-synthesis"):
                return httpx.Response(200, json={"output": {"task_id": "t-1"}})
            return httpx.Response(200, json={"output": {"task_status": "SUCCEEDED"}})

        with pytest.raises(RenderError, match="no video"):
            _provider(handler, poll_interval_seconds=0).render_clip("x")

    def test_it_demands_a_key(self):
        with pytest.raises(ValueError, match="needs an API key"):
            DashScopeVideoProvider(api_key="")


class TestDefaults:
    def test_it_defaults_to_happyhorse(self):
        assert DashScopeVideoProvider(api_key="k").default_video_model == (
            "happyhorse-1.1-t2v"
        )

    def test_the_timeout_allows_for_a_slow_model(self):
        """A 3-second clip took ~100s end to end when measured, so the image
        provider's 120s ceiling is not a safe default here."""
        assert DashScopeVideoProvider(api_key="k").timeout_seconds >= 300


class TestDemoProvider:
    def test_it_needs_no_key(self):
        assert DemoVideoProvider().api_key == "demo"

    def test_it_declines_to_pretend_it_rendered_something(self):
        """There is no offline way to fake b-roll, and returning a blank clip
        would put a black rectangle behind the captions of a real video."""
        with pytest.raises(RenderError, match="no offline"):
            DemoVideoProvider().render_clip("x")


class TestGeneratedClipsAreKept:
    """A generated clip is bought, not computed — so it is kept.

    The studio handed each clip straight to the renderer and dropped it, which
    made every layout change cost the whole storyboard again. On a metered
    trial that is the difference between iterating and not: the first paid
    six-clip render of the demo film was unusable for composition reasons, and
    none of the footage survived to try again with. Cached on disk under a key
    that includes the model, so switching models does not silently reuse the
    old one's output.
    """

    class Counting:
        def __init__(self) -> None:
            self.calls: list[str] = []

        api_key = "k"
        video_model = "happyhorse-1.1-t2v"

        def render_clip(self, prompt: str, *, aspect="9:16", seconds=3) -> bytes:
            self.calls.append(prompt)
            return f"clip-for-{prompt}".encode()

    def test_the_second_ask_does_not_reach_the_vendor(self, tmp_path):
        inner = self.Counting()
        cached = CachingBrollProvider(inner, cache_dir=tmp_path)

        first = cached.render_clip("a sunlit desk", aspect="9:16")
        second = cached.render_clip("a sunlit desk", aspect="9:16")

        assert inner.calls == ["a sunlit desk"]
        assert first == second

    def test_a_different_prompt_is_a_different_clip(self, tmp_path):
        inner = self.Counting()
        cached = CachingBrollProvider(inner, cache_dir=tmp_path)

        cached.render_clip("a sunlit desk", aspect="9:16")
        cached.render_clip("a dark studio", aspect="9:16")

        assert len(inner.calls) == 2

    def test_the_shape_is_part_of_the_key(self, tmp_path):
        """A 9:16 clip is not a 16:9 clip, however alike the prompt."""
        inner = self.Counting()
        cached = CachingBrollProvider(inner, cache_dir=tmp_path)

        cached.render_clip("a sunlit desk", aspect="9:16")
        cached.render_clip("a sunlit desk", aspect="16:9")

        assert len(inner.calls) == 2

    def test_the_model_is_part_of_the_key(self, tmp_path):
        """Switching models must not silently reuse the old one's footage."""
        first = self.Counting()
        CachingBrollProvider(first, cache_dir=tmp_path).render_clip("a desk")

        second = self.Counting()
        # Any model that is not the first one. Named literally rather than
        # derived, so a global rename of the default cannot quietly make the
        # two identical and turn this into a test that always passes.
        second.video_model = "some-other-video-model"
        CachingBrollProvider(second, cache_dir=tmp_path).render_clip("a desk")

        assert second.calls == ["a desk"]

    def test_it_survives_a_new_process(self, tmp_path):
        """The point is iterating across runs, not within one."""
        CachingBrollProvider(self.Counting(), cache_dir=tmp_path).render_clip("a desk")

        inner = self.Counting()
        CachingBrollProvider(inner, cache_dir=tmp_path).render_clip("a desk")

        assert inner.calls == []

    def test_a_failure_is_not_remembered_as_an_answer(self, tmp_path):
        class Failing(self.Counting):
            def render_clip(self, prompt, *, aspect="9:16", seconds=3):
                self.calls.append(prompt)
                raise RenderError("the vendor is down")

        inner = Failing()
        cached = CachingBrollProvider(inner, cache_dir=tmp_path)

        for _ in range(2):
            with pytest.raises(RenderError):
                cached.render_clip("a desk")

        assert len(inner.calls) == 2
