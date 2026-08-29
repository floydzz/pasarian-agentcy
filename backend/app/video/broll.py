"""Generative b-roll — the moving background a scene's captions sit on.

This is deliberately *not* a replacement for `ExplainerRenderer`. The renderer
still draws every word, because exact copy and legible product UI are the two
things a generative video model cannot promise. What a model is good at is the
thing behind the words, so that is all it is asked for.

The DashScope video API is a near-twin of the image one — submit, poll,
download — but not close enough to share code:

- The result is a flat `output.video_url`, not a message envelope.
- The shape parameter is `ratio`. `size` and `aspect_ratio` are accepted and
  then *silently ignored*, and the clip comes back 16:9. Silent, because the
  request succeeds; the only evidence is `usage.ratio` in the response.
- Output carries a burned-in "Happy Horse" watermark unless `watermark` is
  false. `add_watermark` is ignored.
- It is slow: about 100 seconds for a 3-second clip.

All four were measured against the live API on 2026-08-26.
"""

from __future__ import annotations

import base64
import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal
from pathlib import Path

import httpx

from app.media.base import ASPECTS, RenderError

SUBMIT_PATH = "/api/v1/services/aigc/video-generation/video-synthesis"
TASK_PATH = "/api/v1/tasks/{task_id}"

DONE = "SUCCEEDED"
FAILED = {"FAILED", "CANCELED", "UNKNOWN"}

#: What happyhorse accepts per clip. Outside this it refuses the job.
MIN_SECONDS = 3
MAX_SECONDS = 15

#: Generation is slow enough that the image provider's 120s ceiling would
#: abandon almost every clip. This is a hang guard, not a normal wait.
DEFAULT_TIMEOUT_SECONDS = 600

VideoGenerationMode = Literal["text_to_video", "image_to_video", "reference_to_video"]


@dataclass(frozen=True)
class VideoGenerationRequest:
    """One durable AI-video shot request.

    ``render_clip`` below is deliberately still available for the caption-led
    studio.  Cinematic trailers use this richer contract because a prompt-only
    call cannot carry the application image or a visual reference across shots.
    """

    prompt: str
    mode: VideoGenerationMode = "text_to_video"
    aspect: str = "16:9"
    seconds: int = 5
    resolution: Literal["720P", "1080P"] = "1080P"
    reference_images: tuple[bytes, ...] = ()


@dataclass(frozen=True)
class VideoGenerationTask:
    task_id: str
    status: Literal["pending", "running", "succeeded", "failed"]
    video_url: str | None = None
    error: str | None = None


class BrollProvider(ABC):
    """One prompt in, one short clip of video out."""

    base_url: str | None = None

    def __init__(
        self,
        *,
        api_key: str,
        video_model: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not api_key:
            raise ValueError(
                f"{type(self).__name__} needs an API key — set the matching "
                "key in .env before rendering b-roll"
            )
        self.api_key = api_key
        self.video_model = video_model or self.default_video_model
        self.timeout_seconds = timeout_seconds

    @property
    @abstractmethod
    def default_video_model(self) -> str: ...

    @abstractmethod
    def render_clip(
        self, prompt: str, *, aspect: str = "9:16", seconds: int = MIN_SECONDS
    ) -> bytes:
        """MP4 bytes for `prompt`. Raises `RenderError` on failure."""

    def submit_generation(self, request: VideoGenerationRequest) -> VideoGenerationTask:
        """Start a cinematic shot without waiting for the vendor.

        The short-form studio is intentionally synchronous.  A trailer has a
        dozen or more paid remote jobs, so callers persist their task IDs and
        resume them after a refresh instead of holding an HTTP request open.
        Providers that only support the legacy b-roll contract can say so.
        """
        raise RenderError(f"{type(self).__name__} does not support async trailer shots")

    def get_generation(self, task_id: str) -> VideoGenerationTask:
        raise RenderError(f"{type(self).__name__} does not support async trailer shots")

    def download_generation(self, video_url: str) -> bytes:
        raise RenderError(f"{type(self).__name__} does not support async trailer shots")

    @staticmethod
    def _ratio(aspect: str) -> str:
        if aspect not in ASPECTS:
            raise RenderError(
                f"unsupported aspect {aspect!r} — supported: "
                f"{', '.join(sorted(ASPECTS))}"
            )
        return aspect

    @staticmethod
    def _duration(seconds: int) -> int:
        return max(MIN_SECONDS, min(MAX_SECONDS, int(seconds)))


class DashScopeVideoProvider(BrollProvider):
    base_url = "https://dashscope-intl.aliyuncs.com"

    def __init__(self, *, poll_interval_seconds: float = 5.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self.poll_interval_seconds = poll_interval_seconds

    @property
    def default_video_model(self) -> str:
        """Text-to-video, and it has to be.

        This provider sends a prompt and nothing else, so only the `t2v`
        variants can serve it. The `i2v` and `r2v` models in the same family
        require a source image or reference and reject a prompt-only job; the
        failure arrives as a task error after the submit succeeds, which is a
        slow and confusing way to learn you picked the wrong one.
        """
        return "happyhorse-1.1-t2v"

    # Overridden in tests to inject a MockTransport.
    def _client_factory(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=60.0)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def render_clip(
        self, prompt: str, *, aspect: str = "9:16", seconds: int = MIN_SECONDS
    ) -> bytes:
        task = self.submit_generation(
            VideoGenerationRequest(prompt=prompt, aspect=aspect, seconds=seconds,
                                   resolution="720P")
        )
        with self._client_factory() as client:
            url = self._await_result(client, task.task_id)
            return self._download(client, url)

    def submit_generation(self, request: VideoGenerationRequest) -> VideoGenerationTask:
        """Submit one of HappyHorse's T2V/I2V/R2V tasks.

        Image inputs are sent as data URLs rather than an Agentcy ``/media``
        URL: the provider cannot reach a developer's localhost or private
        Docker network.  This also keeps uploaded screenshots private.
        """
        self._validate_request(request)
        with self._client_factory() as client:
            response = self._json(
                client.post(
                    SUBMIT_PATH,
                    headers={**self._headers, "X-DashScope-Async": "enable"},
                    json={
                        "model": self._model_for(request.mode),
                        "input": self._generation_input(request),
                        "parameters": {
                            "ratio": self._ratio(request.aspect),
                            "duration": self._duration(request.seconds),
                            "resolution": request.resolution,
                            "watermark": False,
                        },
                    },
                )
            )
        task_id = response.get("output", {}).get("task_id")
        if not task_id:
            raise RenderError(f"DashScope accepted the job but named no task: {response}")
        return VideoGenerationTask(task_id=task_id, status="pending")

    def get_generation(self, task_id: str) -> VideoGenerationTask:
        with self._client_factory() as client:
            output = self._json(
                client.get(TASK_PATH.format(task_id=task_id), headers=self._headers)
            ).get("output", {})
        state = output.get("task_status", "")
        if state == DONE:
            url = output.get("video_url")
            if not url:
                return VideoGenerationTask(task_id, "failed", error="DashScope returned no video")
            return VideoGenerationTask(task_id, "succeeded", video_url=url)
        if state in FAILED:
            return VideoGenerationTask(
                task_id, "failed", error=output.get("message") or state
            )
        return VideoGenerationTask(task_id, "running" if state == "RUNNING" else "pending")

    def download_generation(self, video_url: str) -> bytes:
        with self._client_factory() as client:
            return self._download(client, video_url)

    # -- steps -------------------------------------------------------------

    def _submit(
        self, client: httpx.Client, prompt: str, *, aspect: str, seconds: int
    ) -> str:
        response = self._json(
            client.post(
                SUBMIT_PATH,
                headers={**self._headers, "X-DashScope-Async": "enable"},
                json={
                    "model": self.video_model,
                    "input": {"prompt": prompt},
                    "parameters": {
                        # `ratio` and only `ratio`. See the module docstring.
                        "ratio": self._ratio(aspect),
                        "duration": self._duration(seconds),
                        "resolution": "720P",
                        # Off, or every client video ships with the vendor's
                        # logo burned into the bottom-right corner.
                        "watermark": False,
                    },
                },
            )
        )
        task_id = response.get("output", {}).get("task_id")
        if not task_id:
            raise RenderError(f"DashScope accepted the job but named no task: {response}")
        return task_id

    def _model_for(self, mode: VideoGenerationMode) -> str:
        """Choose the matching HappyHorse family member for the input mode."""
        suffix = {
            "text_to_video": "t2v",
            "image_to_video": "i2v",
            "reference_to_video": "r2v",
        }[mode]
        if self.video_model.endswith(("-t2v", "-i2v", "-r2v")):
            return self.video_model.rsplit("-", 1)[0] + f"-{suffix}"
        if mode == "text_to_video":
            return self.video_model
        raise RenderError(
            "image and reference trailer shots need a HappyHorse t2v/i2v/r2v "
            f"model family, got {self.video_model!r}"
        )

    @staticmethod
    def _data_url(image: bytes) -> str:
        """Send a PNG-compatible data URL, which DashScope accepts as media."""
        return "data:image/png;base64," + base64.b64encode(image).decode("ascii")

    def _generation_input(self, request: VideoGenerationRequest) -> dict:
        input_data: dict[str, object] = {"prompt": request.prompt}
        if request.mode == "text_to_video":
            return input_data
        image_type = (
            "first_frame" if request.mode == "image_to_video" else "reference_image"
        )
        input_data["media"] = [
            {"type": image_type, "url": self._data_url(image)}
            for image in request.reference_images
        ]
        return input_data

    @staticmethod
    def _validate_request(request: VideoGenerationRequest) -> None:
        if request.mode == "image_to_video" and len(request.reference_images) != 1:
            raise RenderError("image-to-video needs exactly one first-frame image")
        if request.mode == "reference_to_video" and not request.reference_images:
            raise RenderError("reference-to-video needs at least one reference image")

    def _await_result(self, client: httpx.Client, task_id: str) -> str:
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            output = self._json(
                client.get(TASK_PATH.format(task_id=task_id), headers=self._headers)
            ).get("output", {})
            state = output.get("task_status", "")

            if state == DONE:
                url = output.get("video_url")
                if not url:
                    raise RenderError("DashScope reported success but returned no video")
                return url

            if state in FAILED:
                reason = output.get("message") or state
                raise RenderError(f"DashScope could not render this clip: {reason}")

            if time.monotonic() >= deadline:
                raise RenderError(
                    f"DashScope did not finish task {task_id} within "
                    f"{self.timeout_seconds}s — abandoning it"
                )
            time.sleep(self.poll_interval_seconds)

    def _download(self, client: httpx.Client, url: str) -> bytes:
        response = client.get(url, follow_redirects=True)
        if response.status_code >= 400:
            raise RenderError(f"could not download the rendered clip: {response.status_code}")
        return response.content

    @staticmethod
    def _json(response: httpx.Response) -> dict:
        if response.status_code >= 400:
            raise RenderError(
                f"DashScope refused the request ({response.status_code}): {response.text}"
            )
        return response.json()


class CachingBrollProvider(BrollProvider):
    """Another provider, with everything it has already generated kept on disk.

    A clip is bought, not computed. Without this the studio handed each one
    straight to the renderer and dropped it, so every change to the caption
    layout cost the whole storyboard over again — which on a metered trial is
    the difference between being able to iterate and not.

    The key covers the model as well as the prompt and shape, so switching
    models re-generates rather than silently serving the previous model's
    footage. Failures are never cached: a vendor outage is not an answer.
    """

    def __init__(self, inner: BrollProvider, *, cache_dir: Path | str) -> None:
        super().__init__(api_key=inner.api_key, video_model=inner.video_model)
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def default_video_model(self) -> str:
        return self.inner.video_model

    def _key(self, prompt: str, aspect: str, seconds: int) -> Path:
        digest = hashlib.sha256(
            "\x00".join(
                (self.video_model, prompt, aspect, str(seconds))
            ).encode()
        ).hexdigest()
        return self.cache_dir / f"{digest}.mp4"

    def render_clip(
        self, prompt: str, *, aspect: str = "9:16", seconds: int = MIN_SECONDS
    ) -> bytes:
        cached = self._key(prompt, aspect, seconds)
        if cached.exists():
            return cached.read_bytes()

        clip = self.inner.render_clip(prompt, aspect=aspect, seconds=seconds)
        # Written via a temporary name so an interrupted write cannot leave a
        # truncated clip behind that every later run would then trust.
        pending = cached.with_suffix(".partial")
        pending.write_bytes(clip)
        pending.replace(cached)
        return clip

    # Trailer clips are persisted as individual media rows rather than this
    # prompt cache.  Delegate their asynchronous lifecycle unchanged so the
    # higher-level workflow can remember a provider task across page reloads.
    def submit_generation(self, request: VideoGenerationRequest) -> VideoGenerationTask:
        return self.inner.submit_generation(request)

    def get_generation(self, task_id: str) -> VideoGenerationTask:
        return self.inner.get_generation(task_id)

    def download_generation(self, video_url: str) -> bytes:
        return self.inner.download_generation(video_url)


class DemoVideoProvider(BrollProvider):
    """The offline stand-in, which stands in by refusing.

    Every other demo provider fakes its output so `docker compose up` runs the
    whole pipeline with no key. B-roll cannot be faked usefully: a synthetic
    clip is a black rectangle, and a black rectangle behind the captions is
    strictly worse than the deterministic scene the renderer already draws.
    So this says no, and the studio falls back to that scene.
    """

    def __init__(self, *, api_key: str = "demo", **kwargs) -> None:
        super().__init__(api_key=api_key or "demo", **kwargs)

    @property
    def default_video_model(self) -> str:
        return "demo-offline"

    def render_clip(
        self, prompt: str, *, aspect: str = "9:16", seconds: int = MIN_SECONDS
    ) -> bytes:
        raise RenderError(
            "there is no offline b-roll — set VIDEO_PROVIDER=dashscope with a "
            "DASHSCOPE_API_KEY, or render without b-roll"
        )


VIDEO_PROVIDERS: dict[str, type[BrollProvider]] = {
    "dashscope": DashScopeVideoProvider,
    "demo": DemoVideoProvider,
}


def get_video_provider(
    name: str,
    *,
    api_key: str,
    video_model: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> BrollProvider:
    try:
        provider_cls = VIDEO_PROVIDERS[name.strip().lower()]
    except KeyError:
        raise ValueError(
            f"unknown video provider {name!r} — supported: "
            f"{', '.join(sorted(VIDEO_PROVIDERS))}"
        ) from None
    return provider_cls(
        api_key=api_key, video_model=video_model, timeout_seconds=timeout_seconds
    )
