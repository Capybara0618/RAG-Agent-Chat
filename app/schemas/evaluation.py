from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvalCaseCreate(BaseModel):
    question: str
    expected_answer: str = ""
    expected_document_title: str = ""
    task_type: str = "qa"
    required_role: str = "employee"


class EvalRunRead(BaseModel):
    id: str
    status: str
    metrics: dict[str, float]
    failure_examples: list[dict[str, str | float]]
    result_count: int
    created_at: datetime
    completed_at: datetime | None = None


class EvalCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question: str
    expected_answer: str
    expected_document_title: str
    task_type: str
    required_role: str


class EvalRunRequest(BaseModel):
    case_ids: list[str] = Field(default_factory=list)