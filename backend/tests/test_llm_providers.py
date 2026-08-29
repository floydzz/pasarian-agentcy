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

    def test_qwen_defaults_to_a_json_schema_capable_model(self):
        assert self._req(QwenProvider(api_key="k"))["model"] == "qwen3.7-plus"

    def test_qwen_targets_the_dashscope_compatible_endpoint(self):
        assert "dashscope" in QwenProvider(api_key="k").base_url
        assert QwenProvider(api_key="k").base_url.endswith("/compatible-mode/v1")

    def test_qwen_always_names_json_for_structured_output_compatibility(self):
        system = self._req(QwenProvider(api_key="k"))["messages"][0]["content"]
        assert "json" in system.lower()

    def test_openai_uses_its_own_endpoint_not_dashscope(self):
        assert OpenAIProvider(api_key="k").base_url is None


class TestMissingCredentials:
    def test_provider_refuses_to_build_without_an_api_key(self):
        with pytest.raises(ValueError, match="API key"):
            get_provider("claude", api_key="")


import base64

PNG = b"\x89PNG\r\n\x1a\nfake"


class Verdict(BaseModel):
    status: str


def test_openai_compatible_attaches_images_as_data_uris():
    request = OpenAIProvider(api_key="sk-test").build_request(
        system="s", prompt="p", schema=Verdict, images=[PNG]
    )
    content = request["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "p"}
    assert content[1]["type"] == "image_url"
    assert base64.b64encode(PNG).decode() in content[1]["image_url"]["url"]


def test_openai_compatible_keeps_plain_text_when_no_images():
    request = OpenAIProvider(api_key="sk-test").build_request(
        system="s", prompt="p", schema=Verdict
    )
    assert request["messages"][1]["content"] == "p"


def test_demo_provider_accepts_images_and_ignores_them():
    from app.agents.vision_qa import QAVerdict
    from app.llm.demo import DemoProvider

    verdict = DemoProvider().structured(
        system="s", prompt="p", schema=QAVerdict, images=[PNG]
    )
    assert verdict.status in {"passed", "flagged"}


class TestQwenArrayUnwrapping:
    """DashScope wraps the object in a one-element array when an image is sent.

    Verified against the live API on 2026-08-26: `qwen3.7-plus` and
    `qwen3.8-max` both return `[{...}]` for an image call even with
    `strict: true`, while text-only calls return a bare object. The SDK's
    own `.parse()` rejects the array, so the provider unwraps it.
    """

    def test_a_bare_object_parses_unchanged(self):
        assert QwenProvider._coerce('{"status": "passed"}', Verdict).status == "passed"

    def test_a_single_element_array_is_unwrapped(self):
        assert QwenProvider._coerce('[{"status": "passed"}]', Verdict).status == "passed"

    def test_whitespace_and_newlines_do_not_defeat_it(self):
        raw = '[\n  {\n    "status": "flagged"\n  }\n]'
        assert QwenProvider._coerce(raw, Verdict).status == "flagged"

    def test_an_empty_array_is_refused_rather_than_guessed_at(self):
        with pytest.raises(ValueError, match="empty"):
            QwenProvider._coerce("[]", Verdict)

    def test_a_multi_element_array_is_refused_rather_than_guessed_at(self):
        with pytest.raises(ValueError, match="2"):
            QwenProvider._coerce('[{"status": "passed"}, {"status": "flagged"}]', Verdict)


class TestQwenDefaults:
    def test_defaults_to_the_model_that_supports_json_schema(self):
        """`qwen-max` does not support json_schema — verified 400 against the
        live API. Only the 3.7-plus/flash and 3.7/3.8-max series do."""
        assert QwenProvider(api_key="k").default_model == "qwen3.7-plus"


class TestQwenDeliberation:
    """Qwen3 models are hybrid reasoners and DashScope leaves thinking ON.

    Measured against the live API on 2026-08-27, same prompt, same model
    (`qwen3.7-plus`), one call each way:

        thinking ON    37.3s  completion=2096  reasoning=1719  answer=1367 chars
        thinking OFF    6.6s  completion= 338  reasoning=None  answer=1459 chars

    82% of every completion was reasoning nobody reads, for a 5.6x latency
    penalty — and the answer without it came back slightly *longer*. On the
    vision pass the gap was wider still: 42.6s to 2.4s.

    That reasoning was also being billed against `max_completion_tokens`, so a
    16k budget was really a ~14k budget with the rest spent before the answer
    started. Every agent in the pipeline makes this call, so the default is off
    and `reasoning=True` is the deliberate exception.
    """

    def _req(self, **kwargs):
        return QwenProvider(api_key="k", **kwargs).build_request(
            system=SYSTEM, prompt=PROMPT, schema=Sample
        )

    def test_thinking_is_off_unless_asked_for(self):
        assert self._req()["extra_body"]["enable_thinking"] is False

    def test_it_can_be_turned_back_on(self):
        assert self._req(reasoning=True)["extra_body"]["enable_thinking"] is True

    def test_the_switch_is_sent_explicitly_rather_than_left_to_the_gateway(self):
        """DashScope's default is on. Omitting the key is not the same as
        setting it to False, and the difference is the whole fix."""
        assert "enable_thinking" in self._req()["extra_body"]

    def test_the_image_path_carries_it_too(self):
        """The QA pass was the slowest call in the pipeline, not the fastest."""
        request = QwenProvider(api_key="k").build_request(
            system=SYSTEM, prompt=PROMPT, schema=Sample, images=[PNG]
        )
        assert request["extra_body"]["enable_thinking"] is False

    def test_openai_proper_is_left_alone(self):
        """`enable_thinking` is a DashScope extension. Sending it to OpenAI
        would be an unknown parameter on every call."""
        assert "extra_body" not in OpenAIProvider(api_key="k").build_request(
            system=SYSTEM, prompt=PROMPT, schema=Sample
        )


class TestTheRegistryCarriesTheDeliberationSwitch:
    def test_it_reaches_the_provider(self):
        provider = get_provider("qwen", api_key="k", reasoning=True)
        assert provider.reasoning is True

    def test_it_defaults_to_off(self):
        assert get_provider("qwen", api_key="k").reasoning is False

    def test_every_provider_accepts_it(self):
        """It is on the base class, so a provider swap cannot fail on it."""
        for name in ("claude", "openai", "qwen", "demo"):
            assert get_provider(name, api_key="k", reasoning=False).reasoning is False


class TestFailingOverWhenAModelRunsDry:
    """A model whose free quota is spent should step aside, not stop the run.

    This account has hit `AllocationQuota.FreeTierOnly` three times in two
    days — on `happyhorse-1.0-t2v`, on `wan2.7-image`, and on the image model
    mid-campaign, which killed a render pass 0.3s in after the crew had
    already spent eleven minutes writing the variants it was going to render.

    So the text provider carries a queue of models. When the one in hand
    reports its quota exhausted, the next takes over and the call is retried
    rather than lost. Probed live on 2026-08-27: `qwen3.7-plus` and
    `qwen3.6-plus` both answer on this key, and `qwen2.6-plus` does not exist.

    Only quota is failed over. A bad prompt, a malformed schema or a 500 will
    fail identically on the next model, and retrying them would turn one clear
    error into a slow one with the wrong model's name on it.
    """

    class Recording(QwenProvider):
        """A Qwen that answers, or refuses, per model — without a network."""

        def __init__(self, *, dry: set[str], **kwargs) -> None:
            super().__init__(**kwargs)
            self.dry = dry
            self.asked: list[str] = []

        def _call(self, model: str, **_):
            self.asked.append(model)
            if model in self.dry:
                raise RuntimeError(
                    'DashScope refused (403): {"code":"AllocationQuota.'
                    'FreeTierOnly","message":"The free quota has been exhausted."}'
                )
            return Sample(headline=f"from {model}", score=1)

    def _provider(self, dry):
        return self.Recording(
            api_key="k",
            model="qwen3.7-plus",
            fallback_models=["qwen3.6-plus"],
            dry=dry,
        )

    def test_a_healthy_model_is_never_second_guessed(self):
        provider = self._provider(dry=set())
        assert provider.structured(system=SYSTEM, prompt=PROMPT, schema=Sample)
        assert provider.asked == ["qwen3.7-plus"]

    def test_an_exhausted_model_hands_over_to_the_next(self):
        provider = self._provider(dry={"qwen3.7-plus"})
        result = provider.structured(system=SYSTEM, prompt=PROMPT, schema=Sample)
        assert result.headline == "from qwen3.6-plus"
        assert provider.asked == ["qwen3.7-plus", "qwen3.6-plus"]

    def test_the_demotion_sticks_for_the_rest_of_the_run(self):
        """Nine variants must not each pay a 403 to learn what the first one
        already found out."""
        provider = self._provider(dry={"qwen3.7-plus"})
        for _ in range(3):
            provider.structured(system=SYSTEM, prompt=PROMPT, schema=Sample)
        assert provider.asked.count("qwen3.7-plus") == 1

    def test_running_out_of_models_raises_the_last_refusal(self):
        provider = self._provider(dry={"qwen3.7-plus", "qwen3.6-plus"})
        with pytest.raises(RuntimeError, match="AllocationQuota"):
            provider.structured(system=SYSTEM, prompt=PROMPT, schema=Sample)

    def test_an_ordinary_failure_is_not_retried_elsewhere(self):
        class Broken(self.Recording):
            def _call(self, model: str, **_):
                self.asked.append(model)
                raise ValueError("schema rejected by the gateway")

        provider = Broken(
            api_key="k", model="qwen3.7-plus", fallback_models=["qwen3.6-plus"], dry=set()
        )
        with pytest.raises(ValueError, match="schema rejected"):
            provider.structured(system=SYSTEM, prompt=PROMPT, schema=Sample)
        assert provider.asked == ["qwen3.7-plus"]

    def test_with_no_fallbacks_it_behaves_exactly_as_before(self):
        provider = self.Recording(api_key="k", model="qwen3.7-plus", dry={"qwen3.7-plus"})
        with pytest.raises(RuntimeError):
            provider.structured(system=SYSTEM, prompt=PROMPT, schema=Sample)
        assert provider.asked == ["qwen3.7-plus"]


class TestRecognisingAnExhaustedQuota:
    """Matched on the vendor's own error code, not on a status number.

    A 403 can also mean a bad key or a region block, and failing over on those
    would hide a real misconfiguration behind a second model that fails the
    same way.
    """

    def test_the_dashscope_quota_code_counts(self):
        assert QwenProvider.is_quota_exhausted(
            RuntimeError('{"code":"AllocationQuota.FreeTierOnly"}')
        )

    def test_the_plain_english_message_counts_too(self):
        assert QwenProvider.is_quota_exhausted(
            RuntimeError("The free quota has been exhausted.")
        )

    def test_a_bad_key_does_not(self):
        assert not QwenProvider.is_quota_exhausted(
            RuntimeError("403 InvalidApiKey: the key is not valid")
        )

    def test_an_ordinary_failure_does_not(self):
        assert not QwenProvider.is_quota_exhausted(ValueError("bad schema"))
