"""OpenAI and Qwen providers.

Qwen is reached through Alibaba DashScope's OpenAI-compatible gateway, so both
share one request shape and differ only in endpoint and default model.
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from .base import LLMProvider, T


class OpenAICompatibleProvider(LLMProvider):
    def build_request(self, *, system: str, prompt: str,
                      schema: type[T]) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_completion_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "response_format": schema,
        }

    def structured(self, *, system: str, prompt: str, schema: type[T]) -> T:
        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        completion = client.chat.completions.parse(
            **self.build_request(system=system, prompt=prompt, schema=schema)
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
