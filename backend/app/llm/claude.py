"""Anthropic Claude provider — structured output via `messages.parse`."""

from __future__ import annotations

from typing import Any

import anthropic

from .base import LLMProvider, T


class ClaudeProvider(LLMProvider):
    @property
    def default_model(self) -> str:
        return "claude-opus-5"

    def build_request(self, *, system: str, prompt: str,
                      schema: type[T]) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            # Concept planning and director review are both judgement calls —
            # let the model decide how much to think.
            "thinking": {"type": "adaptive"},
            "output_format": schema,
        }

    def structured(self, *, system: str, prompt: str, schema: type[T]) -> T:
        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.parse(
            **self.build_request(system=system, prompt=prompt, schema=schema)
        )
        return response.parsed_output
