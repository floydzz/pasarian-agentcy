"""OpenAI and Qwen providers.

Qwen is reached through Alibaba DashScope's OpenAI-compatible gateway, so both
share one request shape and differ only in endpoint, default model, and one
gateway quirk documented on `QwenProvider`.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
from typing import Any

from openai import OpenAI
from openai.lib._parsing._completions import type_to_response_format_param

from .base import LLMProvider, T

log = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    def build_request(self, *, system: str, prompt: str, schema: type[T],
                      images: list[bytes] | None = None) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_completion_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": self._content(prompt, images)},
            ],
            "response_format": schema,
        }

    @staticmethod
    def _content(prompt: str, images: list[bytes] | None):
        """Plain string when there is nothing to look at — the shape the text
        agents have always sent, kept byte-identical so nothing shifts."""
        if not images:
            return prompt
        return [
            {"type": "text", "text": prompt},
            *(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,"
                        + base64.b64encode(image).decode()
                    },
                }
                for image in images
            ),
        ]

    def _client(self) -> OpenAI:
        """Overridden in tests to avoid reaching the network."""
        return OpenAI(api_key=self.api_key, base_url=self.base_url)

    def structured(self, *, system: str, prompt: str, schema: type[T],
                   images: list[bytes] | None = None) -> T:
        client = self._client()
        completion = client.chat.completions.parse(
            **self.build_request(
                system=system, prompt=prompt, schema=schema, images=images
            )
        )
        return completion.choices[0].message.parsed


class OpenAIProvider(OpenAICompatibleProvider):
    base_url = None

    @property
    def default_model(self) -> str:
        return "gpt-4.1"


class QwenProvider(OpenAICompatibleProvider):
    """Qwen over DashScope, with one deviation from the OpenAI contract.

    When an image is attached, the gateway returns the schema-constrained
    object wrapped in a one-element JSON array — `[{...}]` rather than `{...}`.
    Verified against the live API on 2026-08-26 on both `qwen3.7-plus` and
    `qwen3.8-max`, reproducibly, and `strict: true` does not prevent it.
    Text-only calls are unaffected.

    The SDK's own `.parse()` validates against the schema and so rejects the
    array outright. That failure is quiet in the worst way: `VisionQA` is built
    to degrade to `flagged` rather than block, so every asset would come back
    flagged with a parse error and the QA pass would look like it was running.
    So this provider parses the payload itself and unwraps the array.

    It also carries a queue of models. DashScope's free tier is per model and
    it keeps running dry mid-run — `wan2.7-image` died 0.3s into a render pass
    that the crew had spent eleven minutes preparing for. When the model in
    hand reports its quota spent, the next in `fallback_models` takes over and
    the call is retried; the demotion sticks, so the other eight variants do
    not each pay a 403 to learn what the first one found out.
    """

    #: What DashScope says when a model's free allocation is gone. Matched on
    #: the code rather than the 403, which also covers a bad key and a region
    #: block — failing over on those would hide a misconfiguration behind a
    #: second model that fails in exactly the same way.
    QUOTA_MARKERS = ("allocationquota", "free quota has been exhausted")

    base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._exhausted: set[str] = set()
        # Concepts generate in parallel and variants render in parallel, so
        # several threads can discover the same dry model at once.
        self._guard = threading.Lock()

    @classmethod
    def is_quota_exhausted(cls, error: BaseException) -> bool:
        text = str(error).lower()
        return any(marker in text for marker in cls.QUOTA_MARKERS)

    def _live_models(self) -> list[str]:
        """The models still worth asking, best first.

        If every one is spent the last is returned anyway, so the caller gets
        the vendor's own refusal rather than an invented one — "quota
        exhausted" from DashScope says what to do about it, and a homemade
        "no models left" does not.
        """
        chain = [self.model, *self.fallback_models]
        with self._guard:
            live = [name for name in chain if name not in self._exhausted]
        return live or chain[-1:]

    def build_request(self, *, system: str, prompt: str, schema: type[T],
                      images: list[bytes] | None = None) -> dict[str, Any]:
        """The shared request, plus DashScope's deliberation switch.

        Sent explicitly on every call, never omitted: the gateway's default is
        thinking ON, so leaving the key out is the slow path rather than the
        neutral one. See `TestQwenDeliberation` for what it costs.
        """
        request = super().build_request(
            system=system, prompt=prompt, schema=schema, images=images
        )
        # DashScope rejects `json_object` / JSON-schema output unless one of
        # the messages explicitly contains the word "json".  Individual
        # agents should describe their jobs, not carry an undocumented
        # gateway quirk, so enforce the compatibility contract once here.
        request["messages"][0]["content"] += (
            "\n\nReturn valid JSON that matches the requested response schema."
        )
        request["extra_body"] = {"enable_thinking": self.reasoning}
        return request

    @property
    def default_model(self) -> str:
        # Not `qwen-max`: json_schema output is only supported by the
        # 3.7-plus/flash and 3.7/3.8-max series, and every agent here depends
        # on it. `qwen-max` returns a 400. This model also accepts images, so
        # the text agents and the vision QA pass can share one model.
        return "qwen3.7-plus"

    @staticmethod
    def _coerce(raw: str, schema: type[T]) -> T:
        """Validate `raw` against `schema`, unwrapping DashScope's array."""
        payload = json.loads(raw)
        if isinstance(payload, list):
            if len(payload) != 1:
                raise ValueError(
                    f"DashScope returned {len(payload)} objects where one was "
                    f"asked for; refusing to guess which is the answer"
                    if payload
                    else "DashScope returned an empty array, not an object"
                )
            payload = payload[0]
        return schema.model_validate(payload)

    def _call(self, model: str, *, system: str, prompt: str, schema: type[T],
              images: list[bytes] | None = None) -> T:
        """One attempt, against one named model."""
        request = self.build_request(
            system=system, prompt=prompt, schema=schema, images=images
        )
        request["model"] = model
        # `.create()` rather than `.parse()`: the SDK's parser rejects the
        # wrapped array before this class ever sees it.
        request["response_format"] = type_to_response_format_param(schema)
        completion = self._client().chat.completions.create(**request)
        return self._coerce(completion.choices[0].message.content, schema)

    def structured(self, *, system: str, prompt: str, schema: type[T],
                   images: list[bytes] | None = None) -> T:
        refusal: BaseException | None = None
        for model in self._live_models():
            try:
                return self._call(
                    model, system=system, prompt=prompt, schema=schema, images=images
                )
            except Exception as error:
                # Only quota steps aside. A bad prompt or a malformed schema
                # fails identically on the next model, and retrying it would
                # turn one clear error into a slow one wearing another
                # model's name.
                if not self.is_quota_exhausted(error):
                    raise
                with self._guard:
                    self._exhausted.add(model)
                log.warning(
                    "%s has spent its free quota — falling back to %s",
                    model,
                    ", ".join(self.fallback_models) or "nothing",
                )
                refusal = error
        raise refusal
