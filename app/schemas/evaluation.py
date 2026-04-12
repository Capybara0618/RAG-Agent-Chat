from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvalCaseCreate(BaseModel):
    question: str
    expected_answer: str = ""
    expected_document_title: str = ""
    task_type: str = "qa"
    required_role: str = "manager"
    knowledge_domain: str = "general"


class EvalCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question: str
    expected_answer: str
    expected_document_title: str
    task_type: str
    required_role: str
    knowledge_domain: str


class EvalRunRequest(BaseModel):
    case_ids: list[str] = Field(default_factory=list)
    task_types: list[str] = Field(default_factory=list)
    required_roles: list[str] = Field(default_factory=list)
    knowledge_domains: list[str] = Field(default_factory=list)


class EvalResultRead(BaseModel):
    case_id: str
    answer: str
    score_recall: float
    score_citation: float
    score_safety: float
    passed: bool
    notes: str
    returned_action: str
    failure_tag: str
    trace_id: str


class EvalRunRead(BaseModel):
    id: str
    status: str
    metrics: dict[str, float]
    failure_examples: list[dict[str, str | float]]
    failure_tag_counts: dict[str, int]
    result_count: int
    created_at: datetime
    completed_at: datetime | None = None
    filters: dict[str, object] = Field(default_factory=dict)
    results: list[EvalResultRead] = Field(default_factory=list)
