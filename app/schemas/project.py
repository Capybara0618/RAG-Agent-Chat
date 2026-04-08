from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.chat import QueryResponse


class ProjectCreate(BaseModel):
    title: str
    requester_name: str = ""
    department: str = ""
    vendor_name: str = ""
    category: str = "software"
    budget_amount: float = 0.0
    currency: str = "CNY"
    summary: str = ""
    data_scope: str = "none"


class ProjectAdvanceRequest(BaseModel):
    target_stage: str | None = None


class ProjectTaskCreate(BaseModel):
    stage: str
    task_type: str = "checklist"
    title: str
    details: str = ""
    assignee_role: str = ""
    required: bool = True


class ProjectTaskUpdate(BaseModel):
    status: str


class ProjectArtifactCreate(BaseModel):
    stage: str
    artifact_type: str = "document"
    title: str
    required: bool = True
    document_id: str = ""
    status: str = "provided"
    notes: str = ""


class ProjectArtifactUpdate(BaseModel):
    status: str
    document_id: str = ""
    notes: str = ""


class ProjectReviewRequest(BaseModel):
    query: str
    user_role: str = "employee"
    top_k: int = Field(default=6, ge=1, le=10)


class ProjectTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    stage: str
    task_type: str
    title: str
    details: str
    assignee_role: str
    status: str
    required: bool
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProjectArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    document_id: str
    stage: str
    artifact_type: str
    title: str
    required: bool
    status: str
    notes: str
    created_at: datetime
    updated_at: datetime


class ProjectRiskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    stage: str
    risk_type: str
    severity: str
    summary: str
    status: str
    trace_id: str
    created_at: datetime
    updated_at: datetime


class ProjectDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    stage: str
    decision_type: str
    decision_by: str
    decision_summary: str
    trace_id: str
    created_at: datetime


class ProjectStageRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    stage: str
    status: str
    owner_role: str
    blocking_reason: str
    started_at: datetime
    ended_at: datetime | None


class ProjectSummaryRead(BaseModel):
    id: str
    title: str
    requester_name: str
    department: str
    vendor_name: str
    category: str
    budget_amount: float
    currency: str
    current_stage: str
    risk_level: str
    status: str
    current_owner_role: str
    open_task_count: int
    open_risk_count: int
    created_at: datetime
    updated_at: datetime


class ProjectDetailRead(BaseModel):
    id: str
    title: str
    requester_name: str
    department: str
    vendor_name: str
    category: str
    budget_amount: float
    currency: str
    summary: str
    data_scope: str
    current_stage: str
    risk_level: str
    status: str
    current_owner_role: str
    chat_session_id: str
    blocker_summary: list[str] = Field(default_factory=list)
    tasks: list[ProjectTaskRead] = Field(default_factory=list)
    artifacts: list[ProjectArtifactRead] = Field(default_factory=list)
    risks: list[ProjectRiskRead] = Field(default_factory=list)
    decisions: list[ProjectDecisionRead] = Field(default_factory=list)
    stages: list[ProjectStageRecordRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProjectTimelineEvent(BaseModel):
    kind: str
    stage: str
    title: str
    summary: str
    created_at: datetime
    trace_id: str = ""


class ProjectReviewResult(BaseModel):
    project: ProjectDetailRead
    review: QueryResponse
    risks: list[ProjectRiskRead] = Field(default_factory=list)
