"""Application settings, read from the environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

LLMProviderName = Literal["claude", "openai", "qwen", "demo"]
EmbeddingProviderName = Literal["openai", "qwen", "demo"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str

    llm_provider: LLMProviderName = "claude"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    dashscope_api_key: str = ""

    claude_model: str | None = None
    openai_model: str | None = None
    qwen_model: str | None = None
    demo_model: str | None = None

    #: Never set by a human — keeps the offline provider inside the key lookup.
    demo_api_key: str = "demo"

    embedding_provider: EmbeddingProviderName = "openai"
    openai_embedding_model: str = "text-embedding-3-small"
    qwen_embedding_model: str = "text-embedding-v3"
    demo_embedding_model: str = "demo-offline"

    chroma_path: str = ".chroma"

    serpapi_key: str = ""
    trends_geo: str = "MY"

    #: env var name per provider, so a missing key names itself in the error.
    _KEY_FIELDS = {
        "claude": ("anthropic_api_key", "ANTHROPIC_API_KEY"),
        "openai": ("openai_api_key", "OPENAI_API_KEY"),
        "qwen": ("dashscope_api_key", "DASHSCOPE_API_KEY"),
        # The offline provider needs no key; it still has to answer the lookup.
        "demo": ("demo_api_key", ""),
    }

    def _require_key(self, provider: str) -> str:
        field, env_name = self._KEY_FIELDS[provider]
        key = getattr(self, field)
        if not key:
            raise ValueError(
                f"{provider} is selected but {env_name} is empty — set it in .env"
            )
        return key

    @property
    def active_llm_key(self) -> str:
        return self._require_key(self.llm_provider)

    @property
    def active_llm_model(self) -> str | None:
        return getattr(self, f"{self.llm_provider}_model")

    @property
    def active_embedding_key(self) -> str:
        return self._require_key(self.embedding_provider)

    @property
    def active_embedding_model(self) -> str:
        return getattr(self, f"{self.embedding_provider}_embedding_model")

    @property
    def chroma_dir(self) -> Path:
        path = Path(self.chroma_path)
        return path if path.is_absolute() else REPO_ROOT / "backend" / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
