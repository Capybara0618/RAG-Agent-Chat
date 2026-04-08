from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import TraceStepRead


class TraceRead(BaseModel):
    trace_id: str
    session_id: str
    query: str
    intent: str
    next_action: str
    confidence: float
    final_answer: str
    debug_summary: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    steps: list[TraceStepRead]


class TraceSearchResult(BaseModel):
    trace_id: str
    session_id: str
    query: str
    user_role: str
    intent: str
    next_action: str
    confidence: float
    created_at: datetime
    has_failure: bool
