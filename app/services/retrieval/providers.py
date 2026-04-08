from __future__ import annotations

from typing import Protocol

from app.services.retrieval.service import RetrievedChunk


class EmbeddingProvider(Protocol):
    def embed_text(self, text: str) -> list[float]: ...


class Retriever(Protocol):
    def retrieve(self, db, *, query: str, user_role: str, top_k: int, plan: dict[str, object] | None = None) -> tuple[list[RetrievedChunk], dict[str, object]]: ...


class Reranker(Protocol):
    def rerank(
        self,
        *,
        query: str,
        intent: str,
        query_variants: list[str],
        candidates: list[RetrievedChunk],
        top_k: int,
    ) -> tuple[list[RetrievedChunk], dict[str, object]]: ...
