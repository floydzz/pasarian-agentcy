"""OpenAI and Qwen providers.

Qwen is reached through Alibaba DashScope's OpenAI-compatible gateway, so both
share one request shape and differ only in endpoint and default model.
"""

from __future__ import annotations

import base64
from typing import Any

from openai import OpenAI

from .base import LLMProvider, T


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

    def structured(self, *, system: str, prompt: str, schema: type[T],
                   images: list[bytes] | None = None) -> T:
        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
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
    base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    @property
    def default_model(self) -> str:
        return "qwen-max"
