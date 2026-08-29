"""Alibaba DashScope image synthesis.

Not the OpenAI-compatible gateway `QwenProvider` uses — image synthesis is a
native async task API. Submit, poll, download. The polling loop is bounded by
`timeout_seconds` and gives up with a `RenderError`, because the studio's
resume logic can pick a variant back up later but a hung request during a demo
has nowhere to go.
"""

from __future__ import annotations

import base64
import time

import httpx

from .base import MediaProvider, RenderError

#: The wan2.x generation moved off `text2image/image-synthesis`, which now
#: answers 400 "url error" for every model. Verified live on 2026-08-26.
SUBMIT_PATH = "/api/v1/services/aigc/image-generation/generation"
TASK_PATH = "/api/v1/tasks/{task_id}"

#: Images one edit call may carry. The model rejects a message outside this
#: range with "the last message must contain 1 to 4 images".
MAX_REFERENCE_IMAGES = 4

#: Terminal task states, per DashScope.
DONE = "SUCCEEDED"
FAILED = {"FAILED", "CANCELED", "UNKNOWN"}


class DashScopeMediaProvider(MediaProvider):
    base_url = "https://dashscope-intl.aliyuncs.com"

    def __init__(self, *, poll_interval_seconds: float = 2.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self.poll_interval_seconds = poll_interval_seconds

    @property
    def default_image_model(self) -> str:
        # `wanx2.1-t2i-turbo` is gone — the API answers "Model not exist" —
        # and `wan2.7-image` answered 403 AllocationQuota.FreeTierOnly on
        # 2026-08-27. `wan2.6-image` rendered on the same key that same day.
        # It is slower: one 1024x1024 image measured 166s end to end.
        return "wan2.6-image"

    # Overridden in tests to inject a MockTransport.
    def _client_factory(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=30.0)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def render_image(
        self,
        prompt: str,
        *,
        aspect: str = "1:1",
        reference_images: tuple[bytes, ...] = (),
    ) -> bytes:
        if len(reference_images) > MAX_REFERENCE_IMAGES:
            raise RenderError(
                f"an edit carries 1 to 4 reference images, got "
                f"{len(reference_images)}"
            )
        width, height = self.size_for(aspect)
        with self._client_factory() as client:
            task_id = self._submit(
                client, prompt, f"{width}*{height}", reference_images
            )
            url = self._await_result(client, task_id)
            return self._download(client, url)

    # -- steps -------------------------------------------------------------

    def _submit(
        self,
        client: httpx.Client,
        prompt: str,
        size: str,
        reference_images: tuple[bytes, ...] = (),
    ) -> str:
        # `input.prompt` was the old flat field; the wan2.x models take a
        # message list and ignore the flat one silently.
        content: list[dict[str, str]] = [
            {"image": self._data_url(image)} for image in reference_images
        ]
        content.append({"text": prompt})

        # `enable_interleave` is what tells wan2.6 this is a generation and not
        # an edit. Left off, it reads the call as "change these images" and
        # fails the task with "the last message must contain 1 to 4 images.
        # Got 0" — which is exactly the mode a product-lock render wants, so
        # the flag goes on only when there is nothing to edit from.
        # Sent for every wan model rather than switched on the name: they
        # share this endpoint and envelope, and a parameter one of them
        # ignores costs less than a special case that goes stale the next time
        # a model is swapped.
        parameters: dict[str, object] = {"size": size, "n": 1}
        if not reference_images:
            parameters["enable_interleave"] = True

        response = self._json(
            client.post(
                SUBMIT_PATH,
                headers={**self._headers, "X-DashScope-Async": "enable"},
                json={
                    "model": self.image_model,
                    "input": {"messages": [{"role": "user", "content": content}]},
                    "parameters": parameters,
                },
            )
        )
        task_id = response.get("output", {}).get("task_id")
        if not task_id:
            raise RenderError(f"DashScope accepted the job but named no task: {response}")
        return task_id

    @staticmethod
    def _data_url(image: bytes) -> str:
        """DashScope accepts inline media as a base64 data URL, which keeps the
        product photo off any public URL on its way to the model."""
        return "data:image/png;base64," + base64.b64encode(image).decode("ascii")

    def _await_result(self, client: httpx.Client, task_id: str) -> str:
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            output = self._json(
                client.get(TASK_PATH.format(task_id=task_id), headers=self._headers)
            ).get("output", {})
            state = output.get("task_status", "")

            if state == DONE:
                url = self._image_url(output)
                if not url:
                    raise RenderError("DashScope reported success but returned no image")
                return url

            if state in FAILED:
                reason = output.get("message") or state
                raise RenderError(f"DashScope could not render this prompt: {reason}")

            if time.monotonic() >= deadline:
                raise RenderError(
                    f"DashScope did not finish task {task_id} within "
                    f"{self.timeout_seconds}s — abandoning it"
                )
            time.sleep(self.poll_interval_seconds)

    @staticmethod
    def _image_url(output: dict) -> str | None:
        """Dig the image out of the completion-shaped response.

        The result moved from `output.results[0].url` to a message envelope
        when the endpoint changed, so a shape that looks like a success but
        carries nothing has to read as a failure rather than an empty render.
        """
        choices = output.get("choices") or []
        if not choices:
            return None
        for part in choices[0].get("message", {}).get("content") or []:
            if part.get("image"):
                return part["image"]
        return None

    def _download(self, client: httpx.Client, url: str) -> bytes:
        response = client.get(url)
        if response.status_code >= 400:
            raise RenderError(f"could not download the rendered image: {response.status_code}")
        return response.content

    @staticmethod
    def _json(response: httpx.Response) -> dict:
        if response.status_code >= 400:
            raise RenderError(
                f"DashScope refused the request ({response.status_code}): {response.text}"
            )
        return response.json()
