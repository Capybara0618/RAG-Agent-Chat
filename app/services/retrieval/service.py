from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.security import can_access
from app.repositories.document_repository import DocumentRepository
from app.schemas.common import Citation
from app.services.retrieval.embeddings import EmbeddingService


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_title: str
    location: str
    content: str
    heading: str
    score: float


class RetrievalService:
    def __init__(self, repository: DocumentRepository, embedding_service: EmbeddingService) -> None:
        self.repository = repository
        self.embedding_service = embedding_service

    def rewrite_query(self, query: str) -> str:
        normalized = " ".join(query.strip().split())
        synonyms = {
            "onboarding": "onboarding orientation setup",
            "policy": "policy requirement rule",
            "compare": "difference comparison contrast",
            "sop": "process workflow steps",
        }
        expanded = normalized
        lowered = normalized.lower()
        for trigger, addition in synonyms.items():
            if trigger in lowered and addition not in lowered:
                expanded = f"{expanded} {addition}"
        return expanded.strip()

    def retrieve(self, db: Session, *, query: str, user_role: str, top_k: int) -> list[RetrievedChunk]:
        query_text = self.rewrite_query(query)
        query_tokens = {token.lower() for token in TOKEN_PATTERN.findall(query_text)}
        query_embedding = self.embedding_service.embed_text(query_text)
        scored: list[RetrievedChunk] = []

        for chunk, document in self.repository.fetch_chunks(db):
            if not can_access(user_role, document.allowed_roles.split(",")):
                continue
            chunk_tokens = {token.lower() for token in TOKEN_PATTERN.findall(f"{document.title} {chunk.heading} {chunk.content}")}
            overlap = len(query_tokens & chunk_tokens) / max(len(query_tokens), 1)
            embedding = json.loads(chunk.embedding_json or "[]")
            vector_score = self.embedding_service.cosine_similarity(query_embedding, embedding)
            keyword_bonus = 0.05 if any(token in (chunk.keywords or "") for token in query_tokens) else 0.0
            score = round((0.6 * overlap) + (0.35 * vector_score) + keyword_bonus, 4)
            if score <= 0:
                continue
            scored.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_title=document.title,
                    location=chunk.location,
                    content=chunk.content,
                    heading=chunk.heading,
                    score=score,
                )
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        return self._rerank(scored, top_k=top_k)

    def _rerank(self, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        selected: list[RetrievedChunk] = []
        seen_content: set[str] = set()
        for chunk in chunks:
            fingerprint = chunk.content[:120]
            if fingerprint in seen_content:
                continue
            seen_content.add(fingerprint)
            selected.append(chunk)
            if len(selected) >= top_k:
                break
        return selected

    def compress_context(self, chunks: list[RetrievedChunk], char_budget: int = 2400) -> str:
        parts: list[str] = []
        consumed = 0
        for chunk in chunks:
            block = f"[{chunk.document_title} | {chunk.location}] {chunk.content}".strip()
            if consumed + len(block) > char_budget and parts:
                break
            parts.append(block)
            consumed += len(block)
        return "\n\n".join(parts)

    def to_citations(self, chunks: list[RetrievedChunk]) -> list[Citation]:
        return [
            Citation(
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                location=chunk.location,
                snippet=chunk.content[:240],
                score=chunk.score,
            )
            for chunk in chunks
        ]