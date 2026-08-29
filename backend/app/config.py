"""Application settings, read from the environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

LLMProviderName = Literal["claude", "openai", "qwen", "demo"]
EmbeddingProviderName = Literal["openai", "qwen", "demo"]
MediaProviderName = Literal["dashscope", "demo"]


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

    #: Whether the model deliberates before answering. Off, because DashScope
    #: ships Qwen3 with hidden thinking on and it cost 82% of every completion
    #: for a 5.6x latency penalty when measured — see `TestQwenDeliberation`.
    #: Turn it on to trade the pipeline's speed back for deeper reasoning.
    llm_reasoning: bool = False

    #: Models to fall back to, in order, when the one in use reports its free
    #: quota spent. Comma-separated. DashScope meters per model, so a sibling
    #: usually still answers: `qwen3.6-plus` was live on the same key the day
    #: `wan2.7-image` ran dry. Empty means "fail on the first refusal".
    llm_fallback_models: str = ""

    #: How many concepts the crew works on at once, and how many variants the
    #: studio renders at once. Both loops are vendor round trips with nothing
    #: shared between iterations, so these are the difference between waiting
    #: once and waiting N times. Bounded rather than unlimited because vendors
    #: rate-limit: nine simultaneous image jobs is how a render pass becomes
    #: nine 429s. Set either to 1 to get the old sequential behaviour back.
    crew_lanes: int = 3
    render_lanes: int = 4

    claude_model: str | None = None
    openai_model: str | None = None
    qwen_model: str | None = None
    demo_model: str | None = None

    #: The vision QA pass reads a rendered image; the text agents never do.
    #: Not every model that produces schema-constrained text also accepts an
    #: image, so the role gets its own setting per provider. Unset means "use
    #: the text model", which keeps a one-model setup a one-line setup.
    claude_vision_model: str | None = None
    openai_vision_model: str | None = None
    qwen_vision_model: str | None = None
    demo_vision_model: str | None = None

    #: Never set by a human — keeps the offline provider inside the key lookup.
    demo_api_key: str = "demo"

    embedding_provider: EmbeddingProviderName = "openai"
    openai_embedding_model: str = "text-embedding-3-small"
    qwen_embedding_model: str = "text-embedding-v3"
    demo_embedding_model: str = "demo-offline"

    chroma_path: str = ".chroma"

    #: Defaults to the offline provider for the same reason `llm_provider`
    #: does in compose: `docker compose up` with no keys must run the whole
    #: pipeline and bill nothing.
    media_provider: MediaProviderName = "demo"
    dashscope_image_model: str = "wanx2.1-t2i-turbo"
    demo_image_model: str = "demo-offline"

    assets_path: str = "data/assets"
    media_timeout_seconds: int = 120
    #: A runaway guard, not a normal limit — three concepts at six variants is 18.
    max_renders_per_run: int = 24

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

    #: Media reuses the DashScope account rather than adding a second key.
    _MEDIA_KEY_FIELDS = {
        "dashscope": ("dashscope_api_key", "DASHSCOPE_API_KEY"),
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
    def llm_fallback_chain(self) -> list[str]:
        """The fallback list, split and cleaned. Blanks are dropped so a
        trailing comma in `.env` cannot become a request for model ""."""
        return [
            name.strip()
            for name in self.llm_fallback_models.split(",")
            if name.strip()
        ]

    @property
    def active_llm_model(self) -> str | None:
        return getattr(self, f"{self.llm_provider}_model")

    @property
    def active_vision_model(self) -> str | None:
        return (
            getattr(self, f"{self.llm_provider}_vision_model")
            or self.active_llm_model
        )

    @property
    def active_embedding_key(self) -> str:
        return self._require_key(self.embedding_provider)

    @property
    def active_embedding_model(self) -> str:
        return getattr(self, f"{self.embedding_provider}_embedding_model")

    @property
    def active_media_key(self) -> str:
        field, env_name = self._MEDIA_KEY_FIELDS[self.media_provider]
        key = getattr(self, field)
        if not key:
            raise ValueError(
                f"{self.media_provider} is selected for media but {env_name} "
                "is empty — set it in .env"
            )
        return key

    @property
    def active_media_model(self) -> str:
        return getattr(self, f"{self.media_provider}_image_model")

    @property
    def assets_dir(self) -> Path:
        path = Path(self.assets_path)
        return path if path.is_absolute() else REPO_ROOT / "backend" / path

    @property
    def chroma_dir(self) -> Path:
        path = Path(self.chroma_path)
        return path if path.is_absolute() else REPO_ROOT / "backend" / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
