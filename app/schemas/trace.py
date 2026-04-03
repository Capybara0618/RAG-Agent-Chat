from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import TraceStepRead


class TraceRead(BaseModel):
    trace_id: str
    session_id: str
    query: str
    intent: str
    next_action: str
    confidence: float
    final_answer: str
    created_at: datetime
    steps: list[TraceStepRead]