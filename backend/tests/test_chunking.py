from app.rag.chunking import Chunk, chunk_markdown

DOC = """# Brand Voice

We speak warm, bilingual Manglish-lite. Never clinical.

## Tone rules

Always lead with the humidity problem. Never promise whitening.

## Words we avoid

"Whitening", "fairness", "miracle".
"""


class TestChunkMarkdown:
    def test_splits_on_headings(self):
        chunks = chunk_markdown(DOC, source="brand_voice.md")
        assert [c.heading for c in chunks] == [
            "Brand Voice",
            "Tone rules",
            "Words we avoid",
        ]

    def test_every_chunk_carries_its_source_for_citation(self):
        chunks = chunk_markdown(DOC, source="brand_voice.md")
        assert all(c.source == "brand_voice.md" for c in chunks)

    def test_chunk_ids_are_stable_and_unique(self):
        first = chunk_markdown(DOC, source="brand_voice.md")
        second = chunk_markdown(DOC, source="brand_voice.md")
        assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
        assert len({c.chunk_id for c in first}) == len(first)

    def test_chunk_text_includes_the_heading_so_retrieval_has_context(self):
        body = chunk_markdown(DOC, source="brand_voice.md")[1].text
        assert "Tone rules" in body
        assert "Never promise whitening" in body

    def test_a_long_section_is_split_into_several_chunks(self):
        long_doc = "# Products\n\n" + "\n\n".join(
            f"Paragraph {i} about the serum." for i in range(200)
        )
        chunks = chunk_markdown(long_doc, source="products.md", max_chars=500)
        assert len(chunks) > 1
        assert all(len(c.text) <= 500 for c in chunks)

    def test_ignores_empty_sections(self):
        assert chunk_markdown("# Empty\n\n\n", source="x.md") == []

    def test_document_without_headings_still_produces_a_chunk(self):
        chunks = chunk_markdown("Just some prose about serum.", source="note.md")
        assert len(chunks) == 1
        assert isinstance(chunks[0], Chunk)
        assert chunks[0].heading == "note.md"
