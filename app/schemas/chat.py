from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Citation


class QueryRequest(BaseModel):
    query: str
    session_id: str | None = None
    user_role: str = "employee"
    top_k: int = Field(default=5, ge=1, le=10)


class QueryResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[Citation]
    confidence: float
    trace_id: str
    next_action: str
    intent: str
    debug_summary: dict[str, object] = Field(default_factory=dict)


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    trace_id: str
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime


class SessionRead(BaseModel):
    id: str
    messages: list[ChatMessageRead]


class FeedbackCreate(BaseModel):
    session_id: str
    trace_id: str
    rating: int = Field(ge=-1, le=1)
    corrected_answer: str = ""
    comment: str = ""
    include_in_eval: bool = False


class FeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    trace_id: str
    rating: int
    corrected_answer: str
    comment: str
    include_in_eval: bool
    created_at: datetime
