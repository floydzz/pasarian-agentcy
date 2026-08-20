import pytest

from app.rag.embeddings import (
    EMBEDDERS,
    OpenAIEmbedder,
    QwenEmbedder,
    get_embedder,
)


class FakeEmbeddingsResource:
    """Stands in for `client.embeddings` — records every batch it is handed."""

    def __init__(self, dim: int = 4) -> None:
        self.dim = dim
        self.batches: list[list[str]] = []

    def create(self, *, model: str, input: list[str], **kwargs):
        self.batches.append(list(input))
        data = [
            type("Item", (), {"embedding": [float(len(text))] * self.dim})()
            for text in input
        ]
        return type("Response", (), {"data": data})()


class FakeClient:
    def __init__(self) -> None:
        self.embeddings = FakeEmbeddingsResource()


class TestSelection:
    def test_openai_uses_the_small_embedding_model_by_default(self):
        assert get_embedder("openai", api_key="k").model == "text-embedding-3-small"

    def test_qwen_uses_v3_against_the_dashscope_gateway(self):
        embedder = get_embedder("qwen", api_key="k")
        assert embedder.model == "text-embedding-v3"
        assert "dashscope" in embedder.base_url

    def test_selection_is_case_insensitive(self):
        assert isinstance(get_embedder("OpenAI", api_key="k"), OpenAIEmbedder)

    def test_an_explicit_model_overrides_the_default(self):
        assert get_embedder("openai", api_key="k", model="custom").model == "custom"

    def test_an_unknown_provider_names_the_supported_ones(self):
        with pytest.raises(ValueError) as excinfo:
            get_embedder("cohere", api_key="k")
        message = str(excinfo.value)
        assert all(name in message for name in EMBEDDERS)

    def test_a_missing_api_key_is_rejected_at_construction(self):
        with pytest.raises(ValueError, match="API key"):
            get_embedder("qwen", api_key="")


class TestEmbedding:
    def test_returns_one_vector_per_text_in_order(self):
        client = FakeClient()
        embedder = OpenAIEmbedder(api_key="k", client=client)

        vectors = embedder(["a", "bb", "ccc"])

        assert [v[0] for v in vectors] == [1.0, 2.0, 3.0]

    def test_long_inputs_are_split_into_batches(self):
        client = FakeClient()
        embedder = QwenEmbedder(api_key="k", client=client)  # batch limit of 10

        embedder([f"text {n}" for n in range(25)])

        assert [len(batch) for batch in client.embeddings.batches] == [10, 10, 5]

    def test_batched_results_stay_in_the_original_order(self):
        client = FakeClient()
        embedder = QwenEmbedder(api_key="k", client=client)

        texts = ["x" * n for n in range(1, 26)]
        vectors = embedder(texts)

        assert [v[0] for v in vectors] == [float(n) for n in range(1, 26)]

    def test_embedding_nothing_makes_no_api_call(self):
        client = FakeClient()
        assert OpenAIEmbedder(api_key="k", client=client)([]) == []
        assert client.embeddings.batches == []
