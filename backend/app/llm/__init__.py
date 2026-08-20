"""LLM provider registry — swap providers without touching agent code."""

from __future__ import annotations

from .base import LLMProvider
from .claude import ClaudeProvider
from .openai_compatible import OpenAIProvider, QwenProvider

PROVIDERS: dict[str, type[LLMProvider]] = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "qwen": QwenProvider,
}


def get_provider(name: str, *, api_key: str, model: str | None = None) -> LLMProvider:
    try:
        provider_cls = PROVIDERS[name.strip().lower()]
    except KeyError:
        raise ValueError(
            f"unknown LLM provider {name!r} — supported: "
            f"{', '.join(sorted(PROVIDERS))}"
        ) from None
    return provider_cls(api_key=api_key, model=model)


__all__ = [
    "LLMProvider",
    "ClaudeProvider",
    "OpenAIProvider",
    "QwenProvider",
    "PROVIDERS",
    "get_provider",
]
