from __future__ import annotations

import re

from app.services.ingestion.connectors import SourceSection


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def extract_keywords(text: str, limit: int = 12) -> list[str]:
    tokens = [token.lower() for token in TOKEN_PATTERN.findall(text)]
    scores: dict[str, int] = {}
    for token in tokens:
        if len(token) < 3:
            continue
        scores[token] = scores.get(token, 0) + 1
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _ in ordered[:limit]]


def semantic_chunk_sections(sections: list[SourceSection], max_chars: int = 900) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []

    for section in sections:
        paragraphs = [paragraph.strip() for paragraph in section.content.split("\n\n") if paragraph.strip()]
        if not paragraphs:
            paragraphs = [section.content.strip()]

        current = ""
        chunk_index = 1
        for paragraph in paragraphs:
            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if len(candidate) > max_chars and current:
                chunks.append(
                    {
                        "heading": section.heading,
                        "location": f"{section.location} chunk {chunk_index}",
                        "content": current.strip(),
                        "keywords": extract_keywords(current),
                        "token_count": len(TOKEN_PATTERN.findall(current)),
                        "metadata": section.metadata,
                    }
                )
                chunk_index += 1
                current = paragraph
            else:
                current = candidate

        if current.strip():
            chunks.append(
                {
                    "heading": section.heading,
                    "location": f"{section.location} chunk {chunk_index}",
                    "content": current.strip(),
                    "keywords": extract_keywords(current),
                    "token_count": len(TOKEN_PATTERN.findall(current)),
                    "metadata": section.metadata,
                }
            )

    return chunks