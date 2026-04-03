from __future__ import annotations

from typing import NotRequired, TypedDict

from app.schemas.common import Citation


class AgentState(TypedDict):
    query: str
    session_id: str
    user_role: str
    top_k: int
    history: list[dict[str, str]]
    trace_id: str
    intent: NotRequired[str]
    retrieval_plan: NotRequired[dict[str, object]]
    citations: NotRequired[list[Citation]]
    compressed_context: NotRequired[str]
    draft_answer: NotRequired[str]
    final_answer: NotRequired[str]
    confidence: NotRequired[float]
    next_action: NotRequired[str]
    trace_steps: NotRequired[list[dict[str, object]]]
    retrieved_chunks: NotRequired[list[object]]