from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    document_id: str
    document_title: str
    location: str
    snippet: str
    score: float
    score_breakdown: dict[str, float] = Field(default_factory=dict)


class TraceStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_name: str
    input_summary: str
    output_summary: str
    latency_ms: float
    success: bool
    created_at: datetime
