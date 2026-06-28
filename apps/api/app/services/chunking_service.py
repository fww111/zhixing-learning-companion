from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.material_parser import ParsedPage


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    source_locator: str
    heading: str
    content: str
    token_count: int


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 2)


def chunk_pages(pages: list[ParsedPage], max_chars: int = 1200) -> list[TextChunk]:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than 0")

    chunks: list[TextChunk] = []
    for page in pages:
        content = _normalize_whitespace(page.text)
        if not content:
            continue

        for start in range(0, len(content), max_chars):
            chunk_content = content[start : start + max_chars].strip()
            if not chunk_content:
                continue
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    source_locator=page.source_locator,
                    heading=page.heading,
                    content=chunk_content,
                    token_count=estimate_tokens(chunk_content),
                )
            )

    return chunks


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
