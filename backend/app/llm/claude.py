"""Anthropic Claude provider — structured output via `messages.parse`."""

from __future__ import annotations

import base64
from typing import Any

import anthropic

from .base import LLMProvider, T


class ClaudeProvider(LLMProvider):
    @property
    def default_model(self) -> str:
        return "claude-opus-5"

    @staticmethod
    def _content(prompt: str, images: list[bytes] | None):
        """Images first, then the question — Anthropic's guidance for prompts
        that ask about a picture."""
        if not images:
            return prompt
        return [
            *(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(image).decode(),
                    },
                }
                for image in images
            ),
            {"type": "text", "text": prompt},
        ]

    def build_request(self, *, system: str, prompt: str, schema: type[T],
                      images: list[bytes] | None = None) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [
                {"role": "user", "content": self._content(prompt, images)}
            ],
            # Concept planning and director review are both judgement calls —
            # let the model decide how much to think.
            "thinking": {"type": "adaptive"},
            "output_format": schema,
        }

    def structured(self, *, system: str, prompt: str, schema: type[T],
                   images: list[bytes] | None = None) -> T:
        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.parse(
            **self.build_request(
                system=system, prompt=prompt, schema=schema, images=images
            )
        )
        return response.parsed_output
