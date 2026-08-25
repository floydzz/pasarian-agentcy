"""Alibaba DashScope image synthesis.

Not the OpenAI-compatible gateway `QwenProvider` uses — image synthesis is a
native async task API. Submit, poll, download. The polling loop is bounded by
`timeout_seconds` and gives up with a `RenderError`, because the studio's
resume logic can pick a variant back up later but a hung request during a demo
has nowhere to go.
"""

from __future__ import annotations

import time

import httpx

from .base import MediaProvider, RenderError

SUBMIT_PATH = "/api/v1/services/aigc/text2image/image-synthesis"
TASK_PATH = "/api/v1/tasks/{task_id}"

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
        return "wanx2.1-t2i-turbo"

    # Overridden in tests to inject a MockTransport.
    def _client_factory(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=30.0)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def render_image(self, prompt: str, *, aspect: str = "1:1") -> bytes:
        width, height = self.size_for(aspect)
        with self._client_factory() as client:
            task_id = self._submit(client, prompt, f"{width}*{height}")
            url = self._await_result(client, task_id)
            return self._download(client, url)

    # -- steps -------------------------------------------------------------

    def _submit(self, client: httpx.Client, prompt: str, size: str) -> str:
        response = self._json(
            client.post(
                SUBMIT_PATH,
                headers={**self._headers, "X-DashScope-Async": "enable"},
                json={
                    "model": self.image_model,
                    "input": {"prompt": prompt},
                    "parameters": {"size": size, "n": 1},
                },
            )
        )
        task_id = response.get("output", {}).get("task_id")
        if not task_id:
            raise RenderError(f"DashScope accepted the job but named no task: {response}")
        return task_id

    def _await_result(self, client: httpx.Client, task_id: str) -> str:
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            output = self._json(
                client.get(TASK_PATH.format(task_id=task_id), headers=self._headers)
            ).get("output", {})
            state = output.get("task_status", "")

            if state == DONE:
                results = output.get("results") or []
                url = results[0].get("url") if results else None
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
