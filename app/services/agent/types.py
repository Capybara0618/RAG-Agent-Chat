from __future__ import annotations

from typing import TypedDict
from typing_extensions import NotRequired

from app.schemas.common import Citation, ToolCallRead


class AgentState(TypedDict):
    query: str
    session_id: str
    user_role: str
    top_k: int
    history: list[dict[str, str]]
    trace_id: str
    requested_tools: list[str]
    intent: NotRequired[str]
    intent_confidence: NotRequired[float]
    retrieval_plan: NotRequired[dict[str, object]]
    tool_sequence: NotRequired[list[str]]
    tool_calls: NotRequired[list[ToolCallRead]]
    citations: NotRequired[list[Citation]]
    compressed_context: NotRequired[str]
    retrieval_debug: NotRequired[dict[str, object]]
    comparison_view: NotRequired[dict[str, object]]
    draft_answer: NotRequired[str]
    final_answer: NotRequired[str]
    confidence: NotRequired[float]
    next_action: NotRequired[str]
    verification_debug: NotRequired[dict[str, object]]
    debug_summary: NotRequired[dict[str, object]]
    trace_steps: NotRequired[list[dict[str, object]]]
    retrieved_chunks: NotRequired[list[object]]
