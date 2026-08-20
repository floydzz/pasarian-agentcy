import pytest

from app.config import Settings


def _settings(**over):
    base = dict(
        database_url="mysql+pymysql://u:p@127.0.0.1:3307/agentcy",
        llm_provider="claude",
        anthropic_api_key="ant-key",
        openai_api_key="oa-key",
        dashscope_api_key="ds-key",
    )
    base.update(over)
    return Settings(**base)


class TestActiveLLMKey:
    def test_claude_selects_the_anthropic_key(self):
        assert _settings(llm_provider="claude").active_llm_key == "ant-key"

    def test_openai_selects_the_openai_key(self):
        assert _settings(llm_provider="openai").active_llm_key == "oa-key"

    def test_qwen_selects_the_dashscope_key(self):
        assert _settings(llm_provider="qwen").active_llm_key == "ds-key"

    def test_missing_key_for_the_selected_provider_is_reported_by_name(self):
        with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
            _settings(llm_provider="qwen", dashscope_api_key="").active_llm_key


class TestEmbeddingKey:
    def test_openai_embeddings_use_the_openai_key(self):
        assert _settings(embedding_provider="openai").active_embedding_key == "oa-key"

    def test_qwen_embeddings_use_the_dashscope_key(self):
        assert _settings(embedding_provider="qwen").active_embedding_key == "ds-key"


class TestDefaults:
    def test_trends_default_to_malaysia(self):
        assert _settings().trends_geo == "MY"

    def test_llm_provider_defaults_to_claude(self):
        assert Settings(database_url="mysql+pymysql://u:p@h/d").llm_provider == "claude"

    def test_rejects_an_unsupported_provider(self):
        with pytest.raises(ValueError):
            _settings(llm_provider="llama")
