"""Provider-neutral structured-output interface.

Every agent in the pipeline talks to the LLM through `structured()`, which is
constrained by a Pydantic schema. No agent ever parses free text.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

#: Non-streaming ceiling that stays inside the SDK HTTP timeouts.
DEFAULT_MAX_TOKENS = 16_000


class LLMProvider(ABC):
    """One structured call, one validated Pydantic object back.

    `reasoning` asks the model to deliberate before answering. It lives on the
    base class so that swapping providers can never fail on the keyword, but
    each provider decides what it means and one of them ignores it: DashScope
    ships Qwen3 with hidden thinking ON and charges for it in both latency and
    output budget, so `QwenProvider` sends the switch explicitly. Claude
    manages its own thinking adaptively and spends nothing on a simple call,
    so it is left as it was rather than given a second, conflicting control.

    `fallback_models` is the same arrangement: every provider accepts the
    queue so that swapping one can never fail on the keyword, and
    `QwenProvider` is the one that acts on it, because DashScope's free tier
    is what keeps running dry mid-run.
    """

    #: OpenAI-compatible providers override this with their gateway URL.
    base_url: str | None = None

    def __init__(self, *, api_key: str, model: str | None = None,
                 max_tokens: int = DEFAULT_MAX_TOKENS,
                 reasoning: bool = False,
                 fallback_models: list[str] | None = None) -> None:
        if not api_key:
            raise ValueError(
                f"{type(self).__name__} needs an API key — set the matching "
                "key in .env before running the pipeline"
            )
        self.api_key = api_key
        self.model = model or self.default_model
        self.max_tokens = max_tokens
        self.reasoning = reasoning
        self.fallback_models = list(fallback_models or [])

    @property
    @abstractmethod
    def default_model(self) -> str: ...

    @abstractmethod
    def build_request(self, *, system: str, prompt: str, schema: type[T],
                      images: list[bytes] | None = None) -> dict[str, Any]:
        """Translate a schema-constrained call into provider-specific kwargs."""

    @abstractmethod
    def structured(self, *, system: str, prompt: str, schema: type[T],
                   images: list[bytes] | None = None) -> T:
        """Run the call and return a validated instance of `schema`.

        `images` is for agents that judge a picture rather than text. A provider
        that cannot accept them raises rather than silently reviewing nothing.
        """
