from __future__ import annotations

import re

from app.services.ingestion.connectors import SourceSection
from app.services.retrieval.embeddings import tokenize_text


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def extract_keywords(text: str, limit: int = 12) -> list[str]:
    tokens = [token.lower() for token in tokenize_text(text)]
    scores: dict[str, int] = {}
    for token in tokens:
        if len(token) < 2:
            continue
        scores[token] = scores.get(token, 0) + 1
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _ in ordered[:limit]]


def semantic_chunk_sections(
    sections: list[SourceSection],
    max_chars: int = 600,
    overlap_chars: int = 100,
) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []

    def append_chunk(section: SourceSection, content: str, chunk_index: int) -> None:
        chunks.append(
            {
                "heading": section.heading,
                "location": f"{section.location} chunk {chunk_index}",
                "content": content.strip(),
                "keywords": extract_keywords(content),
                "token_count": len(tokenize_text(content)),
                "metadata": section.metadata,
            }
        )

    def overlap_tail(content: str) -> str:
        if overlap_chars <= 0:
            return ""
        tail = content.strip()[-overlap_chars:]
        boundary = max(tail.rfind("\n\n"), tail.rfind("。"), tail.rfind("；"), tail.rfind("，"))
        if boundary > 20:
            return tail[boundary + 1 :].strip()
        return tail.strip()

    def split_long_paragraph(paragraph: str) -> list[str]:
        text = paragraph.strip()
        if len(text) <= max_chars:
            return [text]
        parts: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + max_chars)
            if end < len(text):
                window = text[start:end]
                boundary = max(window.rfind("。"), window.rfind("；"), window.rfind("，"), window.rfind("\n"))
                if boundary > int(max_chars * 0.55):
                    end = start + boundary + 1
            part = text[start:end].strip()
            if part:
                parts.append(part)
            if end >= len(text):
                break
            start = max(end - overlap_chars, start + 1)
        return parts

    for section in sections:
        raw_paragraphs = [paragraph.strip() for paragraph in section.content.split("\n\n") if paragraph.strip()]
        paragraphs = raw_paragraphs or [section.content.strip()]

        current = ""
        chunk_index = 1
        for paragraph in paragraphs:
            if len(paragraph) > max_chars:
                if current:
                    append_chunk(section, current, chunk_index)
                    chunk_index += 1
                    current = ""
                for part in split_long_paragraph(paragraph):
                    append_chunk(section, part, chunk_index)
                    chunk_index += 1
                continue
            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if len(candidate) > max_chars and current:
                append_chunk(section, current, chunk_index)
                chunk_index += 1
                tail = overlap_tail(current)
                current = f"{tail}\n\n{paragraph}".strip() if tail else paragraph
            else:
                current = candidate

        if current.strip():
            append_chunk(section, current, chunk_index)

    return chunks
