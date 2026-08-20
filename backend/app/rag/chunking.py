"""Markdown chunking for the knowledge corpora.

Chunks are heading-scoped so a retrieved chunk is self-describing — the planning
agent has to cite a specific chunk in `trend_rationale` / `brand_rationale`, and
that citation is only meaningful if the chunk carries its own context.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$", re.MULTILINE)

DEFAULT_MAX_CHARS = 1_200


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    heading: str
    source: str
    #: Position within the source document, so citations can be ordered.
    index: int


def _split_sections(markdown: str, fallback_heading: str) -> list[tuple[str, str]]:
    """Return (heading, body) pairs. A doc with no headings gets one section."""
    matches = list(HEADING.finditer(markdown))
    if not matches:
        return [(fallback_heading, markdown.strip())]

    sections: list[tuple[str, str]] = []
    for position, match in enumerate(matches):
        start = match.end()
        end = matches[position + 1].start() if position + 1 < len(matches) else len(markdown)
        sections.append((match.group(2), markdown[start:end].strip()))
    return sections


def _pack(heading: str, body: str, max_chars: int) -> list[str]:
    """Pack paragraphs under a heading into chunks of at most `max_chars`."""
    prefix = f"{heading}\n\n"
    budget = max_chars - len(prefix)
    chunks: list[str] = []
    current = ""

    for paragraph in (p.strip() for p in body.split("\n\n") if p.strip()):
        # A single oversized paragraph is hard-split rather than dropped.
        while len(paragraph) > budget:
            if current:
                chunks.append(prefix + current)
                current = ""
            chunks.append(prefix + paragraph[:budget])
            paragraph = paragraph[budget:]

        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > budget:
            chunks.append(prefix + current)
            current = paragraph
        else:
            current = candidate

    if current:
        chunks.append(prefix + current)
    return chunks


def chunk_markdown(
    markdown: str, *, source: str, max_chars: int = DEFAULT_MAX_CHARS
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for heading, body in _split_sections(markdown, fallback_heading=source):
        if not body.strip():
            continue
        for text in _pack(heading, body, max_chars):
            digest = hashlib.sha1(
                f"{source}:{len(chunks)}:{text}".encode()
            ).hexdigest()[:16]
            chunks.append(
                Chunk(
                    chunk_id=f"{source}#{len(chunks)}-{digest}",
                    text=text,
                    heading=heading,
                    source=source,
                    index=len(chunks),
                )
            )
    return chunks
