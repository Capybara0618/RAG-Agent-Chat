from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class IndexingTaskStatus(str, Enum):
    uploaded = "uploaded"
    indexing = "indexing"
    indexed = "indexed"
    failed = "failed"


class EvalFailureTag(str, Enum):
    retrieval_miss = "retrieval_miss"
    rerank_error = "rerank_error"
    citation_gap = "citation_gap"
    conflict_unhandled = "conflict_unhandled"
    permission_filtered = "permission_filtered"
    parse_or_chunk_issue = "parse_or_chunk_issue"


class ProcurementStage(str, Enum):
    draft = "draft"
    vendor_onboarding = "vendor_onboarding"
    security_review = "security_review"
    legal_review = "legal_review"
    approval = "approval"
    signing = "signing"
    completed = "completed"
    rejected = "rejected"


class ProcurementProject(Base):
    __tablename__ = "procurement_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), index=True)
    requester_name: Mapped[str] = mapped_column(String(120), default="")
    department: Mapped[str] = mapped_column(String(120), default="")
    vendor_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    category: Mapped[str] = mapped_column(String(120), default="")
    budget_amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(12), default="CNY")
    summary: Mapped[str] = mapped_column(Text, default="")
    data_scope: Mapped[str] = mapped_column(String(50), default="none")
    current_stage: Mapped[str] = mapped_column(String(50), default=ProcurementStage.draft.value, index=True)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    current_owner_role: Mapped[str] = mapped_column(String(50), default="business")
    chat_session_id: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ProjectStageRecord(Base):
    __tablename__ = "project_stage_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("procurement_projects.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    owner_role: Mapped[str] = mapped_column(String(50), default="")
    blocking_reason: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProjectTask(Base):
    __tablename__ = "project_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("procurement_projects.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(50), index=True)
    task_type: Mapped[str] = mapped_column(String(50), default="checklist")
    title: Mapped[str] = mapped_column(String(255))
    details: Mapped[str] = mapped_column(Text, default="")
    assignee_role: Mapped[str] = mapped_column(String(50), default="")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ProjectArtifact(Base):
    __tablename__ = "project_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("procurement_projects.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    stage: Mapped[str] = mapped_column(String(50), index=True)
    artifact_type: Mapped[str] = mapped_column(String(80), default="document")
    title: Mapped[str] = mapped_column(String(255))
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default="missing", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ProjectDecision(Base):
    __tablename__ = "project_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("procurement_projects.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(50), index=True)
    decision_type: Mapped[str] = mapped_column(String(50), default="ai_review")
    decision_by: Mapped[str] = mapped_column(String(50), default="system")
    decision_summary: Mapped[str] = mapped_column(Text, default="")
    trace_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProjectRisk(Base):
    __tablename__ = "project_risks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("procurement_projects.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(50), index=True)
    risk_type: Mapped[str] = mapped_column(String(80), default="general")
    severity: Mapped[str] = mapped_column(String(30), default="medium")
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    trace_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), index=True)
    source_type: Mapped[str] = mapped_column(String(50))
    source_path: Mapped[str] = mapped_column(Text, default="")
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    allowed_roles: Mapped[str] = mapped_column(String(120), default="guest,employee,admin")
    tags: Mapped[str] = mapped_column(String(255), default="")
    parse_status: Mapped[str] = mapped_column(String(50), default=IndexingTaskStatus.uploaded.value)
    status: Mapped[str] = mapped_column(String(50), default=IndexingTaskStatus.uploaded.value, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    last_error: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str] = mapped_column(String(255), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text)
    keywords: Mapped[str] = mapped_column(Text, default="")
    embedding_json: Mapped[str] = mapped_column(Text, default="[]")
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), default="New Session")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    trace_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    citations_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TraceRecord(Base):
    __tablename__ = "trace_records"

    trace_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    user_role: Mapped[str] = mapped_column(String(50))
    query: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(50), default="")
    next_action: Mapped[str] = mapped_column(String(50), default="answer")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    final_answer: Mapped[str] = mapped_column(Text, default="")
    debug_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TraceStep(Base):
    __tablename__ = "trace_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    trace_id: Mapped[str] = mapped_column(ForeignKey("trace_records.trace_id", ondelete="CASCADE"), index=True)
    node_name: Mapped[str] = mapped_column(String(100))
    input_summary: Mapped[str] = mapped_column(Text, default="")
    output_summary: Mapped[str] = mapped_column(Text, default="")
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EvalCase(Base):
    __tablename__ = "eval_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    question: Mapped[str] = mapped_column(Text)
    expected_answer: Mapped[str] = mapped_column(Text, default="")
    expected_document_title: Mapped[str] = mapped_column(String(255), default="")
    task_type: Mapped[str] = mapped_column(String(50), default="qa", index=True)
    required_role: Mapped[str] = mapped_column(String(50), default="employee", index=True)
    knowledge_domain: Mapped[str] = mapped_column(String(100), default="general", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String(50), default="running")
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    failure_examples_json: Mapped[str] = mapped_column(Text, default="[]")
    failure_tag_counts_json: Mapped[str] = mapped_column(Text, default="{}")
    filters_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("eval_runs.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("eval_cases.id", ondelete="CASCADE"), index=True)
    answer: Mapped[str] = mapped_column(Text, default="")
    score_recall: Mapped[float] = mapped_column(Float, default=0.0)
    score_citation: Mapped[float] = mapped_column(Float, default=0.0)
    score_safety: Mapped[float] = mapped_column(Float, default=0.0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    returned_action: Mapped[str] = mapped_column(String(50), default="answer")
    failure_tag: Mapped[str] = mapped_column(String(80), default="")
    trace_id: Mapped[str] = mapped_column(String(36), default="", index=True)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    rating: Mapped[int] = mapped_column(Integer, default=0)
    corrected_answer: Mapped[str] = mapped_column(Text, default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    include_in_eval: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String(50), default="pending")
    candidate_case_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class IndexingTask(Base):
    __tablename__ = "indexing_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    source_name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(50), default="")
    source_path: Mapped[str] = mapped_column(Text, default="")
    remote_url: Mapped[str] = mapped_column(Text, default="")
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    allowed_roles: Mapped[str] = mapped_column(String(120), default="guest,employee,admin")
    tags: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(50), default=IndexingTaskStatus.uploaded.value, index=True)
    duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
