from __future__ import annotations

import re

from app.schemas.common import Citation
from app.services.retrieval.service import RetrievedChunk


SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")


class LLMClient:
    def __init__(self, *, api_base: str = "", api_key: str = "", model: str = "") -> None:
        self.api_base = api_base
        self.api_key = api_key
        self.model = model

    def route_intent(self, query: str) -> str:
        lowered = query.lower()
        if any(token in lowered for token in ["difference", "compare", "versus", "vs"]):
            return "compare"
        if any(token in lowered for token in ["workflow", "sop", "process", "steps", "how do i"]):
            return "workflow"
        if any(token in lowered for token in ["onboarding", "new hire", "access", "support", "help desk"]):
            return "support"
        return "qa"

    def build_retrieval_plan(self, query: str, intent: str, top_k: int) -> dict[str, object]:
        return {
            "top_k": top_k + 1 if intent == "compare" else top_k,
            "expand_query": intent in {"compare", "workflow"},
            "allow_multi_doc": intent in {"compare", "workflow"},
            "query": query,
        }

    def compose_answer(
        self,
        *,
        query: str,
        intent: str,
        citations: list[Citation],
        retrieved_chunks: list[RetrievedChunk],
        history: list[dict[str, str]],
    ) -> tuple[str, float, str]:
        if not citations:
            if len(query.split()) <= 4:
                return (
                    "I could not ground an answer in the knowledge base yet. Please clarify the department, policy, or document scope you want me to search.",
                    0.18,
                    "clarify",
                )
            return (
                "I do not have enough grounded evidence in the knowledge base to answer this safely. Please upload a relevant source or narrow the question.",
                0.12,
                "refuse",
            )

        if intent == "compare":
            return self._compose_compare_answer(query, retrieved_chunks)
        if intent == "workflow":
            return self._compose_workflow_answer(query, retrieved_chunks)
        if intent == "support":
            return self._compose_support_answer(retrieved_chunks)
        return self._compose_qa_answer(retrieved_chunks, bool(history))

    def _compose_compare_answer(self, query: str, retrieved_chunks: list[RetrievedChunk]) -> tuple[str, float, str]:
        grouped: dict[str, list[RetrievedChunk]] = {}
        for chunk in retrieved_chunks:
            grouped.setdefault(chunk.document_title, []).append(chunk)
        lines = [f"Comparison for: {query}"]
        for title, chunks in list(grouped.items())[:3]:
            lines.append(f"- {title}: {self._first_sentence(chunks[0].content)}")
        lines.append("Key takeaway: the differences above are grounded in the cited source snippets.")
        return ("\n".join(lines), 0.79, "answer")

    def _compose_workflow_answer(self, query: str, retrieved_chunks: list[RetrievedChunk]) -> tuple[str, float, str]:
        steps: list[str] = []
        for chunk in retrieved_chunks[:3]:
            for sentence in SENTENCE_PATTERN.split(chunk.content):
                cleaned = sentence.strip()
                if cleaned and cleaned not in steps:
                    steps.append(cleaned)
                if len(steps) >= 4:
                    break
            if len(steps) >= 4:
                break

        if not steps:
            return (
                "I found related evidence but not enough step-by-step detail to produce a reliable SOP. Please narrow the scope or upload the detailed procedure document.",
                0.33,
                "clarify",
            )

        lines = [f"Suggested workflow for: {query}"]
        for index, step in enumerate(steps, start=1):
            lines.append(f"{index}. {step}")
        lines.append("Review the cited sections before operational use.")
        return ("\n".join(lines), 0.74, "answer")

    def _compose_support_answer(self, retrieved_chunks: list[RetrievedChunk]) -> tuple[str, float, str]:
        chunk = retrieved_chunks[0]
        lines = [
            f"Grounded answer: {self._first_sentence(chunk.content)}",
            "Recommended next action: follow the cited policy or onboarding source and escalate if your case is outside the documented path.",
        ]
        return ("\n".join(lines), 0.76, "answer")

    def _compose_qa_answer(self, retrieved_chunks: list[RetrievedChunk], has_history: bool) -> tuple[str, float, str]:
        primary = retrieved_chunks[0]
        answer = self._first_sentence(primary.content)
        if len(retrieved_chunks) > 1:
            answer = f"{answer} Supporting evidence also appears in {retrieved_chunks[1].document_title}."
        if has_history:
            answer = f"{answer} This answer also considers the active session context."
        return (answer, 0.81, "answer")

    def verify_citations(self, answer: str, citations: list[Citation]) -> tuple[float, str]:
        if not citations:
            return 0.1, "refuse"
        answer_tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9_]+", answer)}
        evidence_tokens = set()
        for citation in citations:
            evidence_tokens.update(token.lower() for token in re.findall(r"[A-Za-z0-9_]+", citation.snippet))
        overlap = len(answer_tokens & evidence_tokens) / max(len(answer_tokens), 1)
        if overlap < 0.18:
            return 0.38, "clarify"
        return min(0.92, 0.55 + overlap), "answer"

    @staticmethod
    def _first_sentence(text: str) -> str:
        sentences = [sentence.strip() for sentence in SENTENCE_PATTERN.split(text) if sentence.strip()]
        if not sentences:
            return text[:180]
        return sentences[0]