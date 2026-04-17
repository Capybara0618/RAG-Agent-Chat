from __future__ import annotations

from typing import Protocol

from app.schemas.common import Citation
from app.services.retrieval.service import RetrievedChunk


class LLMProvider(Protocol):
    def classify_intent(self, query: str) -> tuple[str, float]: ...

    def build_retrieval_plan(self, query: str, intent: str, top_k: int) -> dict[str, object]: ...

    def extract_supplier_profile(
        self,
        *,
        project_context: dict[str, str],
        combined_text: str,
        material_names: list[str],
    ) -> dict[str, object] | None: ...

    def compose_answer(
        self,
        *,
        query: str,
        intent: str,
        citations: list[Citation],
        retrieved_chunks: list[RetrievedChunk],
        comparison_view: dict[str, object] | None,
        history: list[dict[str, str]],
    ) -> tuple[str, float, str]: ...

    def verify_citations(self, answer: str, citations: list[Citation]) -> tuple[float, str, dict[str, object]]: ...
