"""LLM provider registry — swap providers without touching agent code."""

from __future__ import annotations

from .base import LLMProvider
from .claude import ClaudeProvider
from .demo import DemoProvider
from .openai_compatible import OpenAIProvider, QwenProvider

PROVIDERS: dict[str, type[LLMProvider]] = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "qwen": QwenProvider,
    # Offline rehearsal — see app/llm/demo.py. Not a model.
    "demo": DemoProvider,
}


def get_provider(
    name: str,
    *,
    api_key: str,
    model: str | None = None,
    reasoning: bool = False,
    fallback_models: list[str] | None = None,
) -> LLMProvider:
    try:
        provider_cls = PROVIDERS[name.strip().lower()]
    except KeyError:
        raise ValueError(
            f"unknown LLM provider {name!r} — supported: "
            f"{', '.join(sorted(PROVIDERS))}"
        ) from None
    return provider_cls(
        api_key=api_key,
        model=model,
        reasoning=reasoning,
        fallback_models=fallback_models,
    )


__all__ = [
    "LLMProvider",
    "ClaudeProvider",
    "OpenAIProvider",
    "QwenProvider",
    "DemoProvider",
    "PROVIDERS",
    "get_provider",
]
