import pytest
from pydantic import BaseModel

from app.llm import ClaudeProvider, OpenAIProvider, QwenProvider, get_provider


class Sample(BaseModel):
    headline: str
    score: int


SYSTEM = "You are a planner."
PROMPT = "Give me one headline."


class TestRegistry:
    def test_resolves_each_supported_provider(self):
        assert isinstance(get_provider("claude", api_key="k"), ClaudeProvider)
        assert isinstance(get_provider("openai", api_key="k"), OpenAIProvider)
        assert isinstance(get_provider("qwen", api_key="k"), QwenProvider)

    def test_provider_name_is_case_insensitive(self):
        assert isinstance(get_provider("Claude", api_key="k"), ClaudeProvider)

    def test_unknown_provider_names_the_supported_ones(self):
        with pytest.raises(ValueError, match="claude"):
            get_provider("llama", api_key="k")


class TestClaudeRequestShape:
    def _req(self, **kw):
        return ClaudeProvider(api_key="k", **kw).build_request(
            system=SYSTEM, prompt=PROMPT, schema=Sample
        )

    def test_defaults_to_opus_5(self):
        assert self._req()["model"] == "claude-opus-5"

    def test_uses_adaptive_thinking(self):
        assert self._req()["thinking"] == {"type": "adaptive"}

    def test_passes_the_pydantic_schema_as_output_format(self):
        assert self._req()["output_format"] is Sample

    def test_system_prompt_is_top_level_not_a_message(self):
        req = self._req()
        assert req["system"] == SYSTEM
        assert req["messages"] == [{"role": "user", "content": PROMPT}]

    def test_model_is_overridable(self):
        assert self._req(model="claude-sonnet-5")["model"] == "claude-sonnet-5"


class TestOpenAICompatibleRequestShape:
    def _req(self, provider):
        return provider.build_request(system=SYSTEM, prompt=PROMPT, schema=Sample)

    def test_openai_sends_system_and_user_messages(self):
        req = self._req(OpenAIProvider(api_key="k"))
        assert req["messages"] == [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": PROMPT},
        ]

    def test_openai_constrains_output_with_the_pydantic_schema(self):
        assert self._req(OpenAIProvider(api_key="k"))["response_format"] is Sample

    def test_qwen_defaults_to_qwen_max(self):
        assert self._req(QwenProvider(api_key="k"))["model"] == "qwen-max"

    def test_qwen_targets_the_dashscope_compatible_endpoint(self):
        assert "dashscope" in QwenProvider(api_key="k").base_url
        assert QwenProvider(api_key="k").base_url.endswith("/compatible-mode/v1")

    def test_openai_uses_its_own_endpoint_not_dashscope(self):
        assert OpenAIProvider(api_key="k").base_url is None


class TestMissingCredentials:
    def test_provider_refuses_to_build_without_an_api_key(self):
        with pytest.raises(ValueError, match="API key"):
            get_provider("claude", api_key="")
