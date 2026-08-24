"""Chroma-backed knowledge store.

Two corpora, two collections, never merged into one index. The company KB is
ground truth about the brand; the trend corpus is inspiration only. Mixing them
would let a passing TikTok hashtag masquerade as a brand fact, so retrieval is
deliberately split into two methods with no shared query path.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.api.types import EmbeddingFunction
from chromadb.utils.embedding_functions import register_embedding_function

from app.rag.chunking import DEFAULT_MAX_CHARS, Chunk, chunk_markdown

COMPANY_KB = "company_kb"
TREND_CORPUS = "trend_corpus"

#: Takes a batch of texts, returns one vector per text.
Embedder = Callable[[list[str]], list[list[float]]]


@dataclass(frozen=True)
class Retrieved:
    chunk_id: str
    text: str
    heading: str
    source: str
    #: Chroma's cosine distance — lower is closer.
    distance: float

    def citation(self) -> str:
        """The form an agent quotes back in its rationale fields."""
        return f"{self.source} § {self.heading} ({self.chunk_id})"


def _no_embedder(texts: list[str]) -> list[list[float]]:
    raise RuntimeError(
        "this store was rehydrated from persisted config; construct "
        "KnowledgeStore with an embedder to query it"
    )


@register_embedding_function
class _ChromaEmbedder(EmbeddingFunction):
    """Adapts our plain callable to the interface Chroma expects.

    The embedder itself is injected by the caller and never persisted — which
    provider does the embedding is a runtime setting, not a property of the
    collection on disk.
    """

    def __init__(self, embedder: Embedder = _no_embedder) -> None:
        self._embedder = embedder

    def __call__(self, input: Sequence[str]) -> list[list[float]]:  # noqa: A002
        return self._embedder(list(input))

    @staticmethod
    def name() -> str:
        return "agentcy-embedder"

    def get_config(self) -> dict:
        return {}

    @staticmethod
    def build_from_config(config: dict) -> "_ChromaEmbedder":
        return _ChromaEmbedder()


class KnowledgeStore:
    def __init__(self, *, path: Path | str, embedder: Embedder) -> None:
        self._client = chromadb.PersistentClient(path=str(path))
        self._embedding_function = _ChromaEmbedder(embedder)

    def _collection(self, name: str):
        return self._client.get_or_create_collection(
            name=name,
            embedding_function=self._embedding_function,
            metadata={"hnsw:space": "cosine"},
        )

    # -- ingestion ---------------------------------------------------------

    def ingest_company_kb(
        self, markdown: str, *, source: str, max_chars: int = DEFAULT_MAX_CHARS
    ) -> int:
        return self._ingest(COMPANY_KB, markdown, source=source, max_chars=max_chars)

    def ingest_trends(
        self, markdown: str, *, source: str, max_chars: int = DEFAULT_MAX_CHARS
    ) -> int:
        return self._ingest(TREND_CORPUS, markdown, source=source, max_chars=max_chars)

    def _ingest(
        self, collection_name: str, markdown: str, *, source: str, max_chars: int
    ) -> int:
        chunks = chunk_markdown(markdown, source=source, max_chars=max_chars)
        if not chunks:
            return 0

        # Upsert keyed on chunk_id: re-running ingestion after an edit replaces
        # the chunk in place instead of stacking a second copy beside it.
        self._collection(collection_name).upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            metadatas=[self._metadata(chunk) for chunk in chunks],
        )
        return len(chunks)

    @staticmethod
    def _metadata(chunk: Chunk) -> dict[str, str | int]:
        return {"heading": chunk.heading, "source": chunk.source, "index": chunk.index}

    # -- retrieval ---------------------------------------------------------

    def retrieve_company(self, query: str, *, k: int = 4) -> list[Retrieved]:
        return self._retrieve(COMPANY_KB, query, k)

    def retrieve_trends(self, query: str, *, k: int = 4) -> list[Retrieved]:
        return self._retrieve(TREND_CORPUS, query, k)

    def _retrieve(self, collection_name: str, query: str, k: int) -> list[Retrieved]:
        collection = self._collection(collection_name)
        available = collection.count()
        if not available:
            return []

        result = collection.query(query_texts=[query], n_results=min(k, available))
        return [
            Retrieved(
                chunk_id=chunk_id,
                text=document,
                heading=str(metadata.get("heading", "")),
                source=str(metadata.get("source", "")),
                distance=float(distance),
            )
            for chunk_id, document, metadata, distance in zip(
                result["ids"][0],
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
                strict=True,
            )
        ]

    def count(self, collection_name: str) -> int:
        return self._collection(collection_name).count()

    # -- inspection --------------------------------------------------------

    def sources(self, collection_name: str) -> list["StoredSource"]:
        """What documents a corpus is made of, and how much of each.

        Retrieval is invisible by nature — a person tuning a watchlist is
        otherwise trusting that a scrape landed somewhere. This is the check:
        it reads the collection itself rather than the directory on disk, so a
        file that was written but never ingested does not appear here.
        """
        collection = self._collection(collection_name)
        if not collection.count():
            return []

        # Documents are excluded: this is a manifest, not a corpus dump.
        result = collection.get(include=["metadatas"])
        counts: dict[str, int] = {}
        headings: dict[str, str] = {}
        for metadata in result["metadatas"] or []:
            source = str(metadata.get("source", "unknown"))
            counts[source] = counts.get(source, 0) + 1
            # The first heading in a document names it better than its filename.
            if metadata.get("index") == 0:
                headings[source] = str(metadata.get("heading", ""))

        return sorted(
            (
                StoredSource(
                    source=source, chunks=chunks, heading=headings.get(source, "")
                )
                for source, chunks in counts.items()
            ),
            key=lambda stored: stored.source,
        )


@dataclass(frozen=True)
class StoredSource:
    """One ingested document, as the collection holds it."""

    source: str
    chunks: int
    heading: str
