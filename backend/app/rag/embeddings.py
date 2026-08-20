"""Embedding providers for the two knowledge corpora.

Both supported providers speak the OpenAI embeddings shape, so the difference
between them is a base URL, a model name, and a batch limit. Whichever one is
active must stay fixed for the life of a Chroma collection — vectors from two
different models are not comparable, so switching providers means re-ingesting.
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI


class BaseEmbedder:
    """Embeds batches of text through an OpenAI-compatible endpoint."""

    #: `None` means the SDK's own default host.
    base_url: str | None = None
    default_model: str
    #: Per-request input limit imposed by the provider.
    batch_size: int = 100
    env_var: str

    def __init__(
        self,
        *,
        api_key: str,
        model: str | None = None,
        client: Any | None = None,
    ) -> None:
        if not api_key:
            raise ValueError(f"missing API key — set {self.env_var}")
        self.api_key = api_key
        self.model = model or self.default_model
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def __call__(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            response = self.client.embeddings.create(model=self.model, input=batch)
            vectors.extend(item.embedding for item in response.data)
        return vectors


class OpenAIEmbedder(BaseEmbedder):
    default_model = "text-embedding-3-small"
    env_var = "OPENAI_API_KEY"


class QwenEmbedder(BaseEmbedder):
    base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    default_model = "text-embedding-v3"
    # DashScope rejects more than 10 inputs per embeddings request.
    batch_size = 10
    env_var = "DASHSCOPE_API_KEY"


EMBEDDERS: dict[str, type[BaseEmbedder]] = {
    "openai": OpenAIEmbedder,
    "qwen": QwenEmbedder,
}


def get_embedder(
    provider: str, *, api_key: str, model: str | None = None, client: Any | None = None
) -> BaseEmbedder:
    try:
        embedder_class = EMBEDDERS[provider.lower()]
    except KeyError:
        supported = ", ".join(sorted(EMBEDDERS))
        raise ValueError(
            f"unknown embedding provider {provider!r} — supported: {supported}"
        ) from None
    return embedder_class(api_key=api_key, model=model, client=client)
