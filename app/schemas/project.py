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
    business_value: str = ""
    target_go_live_date: str = ""
    data_scope: str = "none"


class ProjectUpdate(BaseModel):
    title: str | None = None
    requester_name: str | None = None
    department: str | None = None
    vendor_name: str | None = None
    category: str | None = None
    budget_amount: float | None = None
    currency: str | None = None
    summary: str | None = None
    business_value: str | None = None
    target_go_live_date: str | None = None
    data_scope: str | None = None


class ProjectSubmitRequest(BaseModel):
    actor_role: str = "business"
    reason: str = ""


class ProjectWithdrawRequest(BaseModel):
    actor_role: str = "business"
    reason: str = Field(min_length=1)


class ProjectManagerDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approve|return)$")
    actor_role: str = "manager"
    reason: str = ""


class ProjectLegalDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approve|return)$")
    actor_role: str = "legal"
    reason: str = ""


class ProjectFinalApproveRequest(BaseModel):
    actor_role: str = "manager"
    reason: str = ""


class ProjectFinalReturnRequest(BaseModel):
    actor_role: str = "manager"
    target_stage: str = Field(pattern="^(legal_review|procurement_sourcing)$")
    reason: str = Field(min_length=1)


class ProjectCancelRequest(BaseModel):
    actor_role: str = "business"
    reason: str = Field(min_length=1)


class ProjectSignRequest(BaseModel):
    actor_role: str = "admin"
    reason: str = ""


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
    linked_vendor_id: str = ""
    direction: str = "internal"
    version_no: int = 1
    status: str = "provided"
    notes: str = ""


class ProjectArtifactUpdate(BaseModel):
    status: str
    document_id: str | None = None
    linked_vendor_id: str | None = None
    direction: str | None = None
    version_no: int | None = None
    notes: str | None = None


class VendorCandidateCreate(BaseModel):
    vendor_name: str
    source_platform: str = ""
    source_url: str = ""
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    profile_summary: str = ""
    procurement_notes: str = ""
    handles_company_data: bool = False
    requires_system_integration: bool = False
    quoted_amount: float = 0.0


class VendorReviewRequest(BaseModel):
    query: str
    user_role: str = "procurement"
    top_k: int = Field(default=6, ge=1, le=10)


class ProcurementAgentReviewRequest(BaseModel):
    vendor_name: str
    source_platform: str = ""
    source_url: str = ""
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    profile_summary: str = ""
    procurement_notes: str = ""
    handles_company_data: bool = False
    requires_system_integration: bool = False
    quoted_amount: float = 0.0
    supplier_profile: SupplierProfileRead | None = None
    focus_points: str = ""
    user_role: str = "procurement"
    top_k: int = Field(default=6, ge=1, le=10)


class ProcurementMaterialRead(BaseModel):
    name: str
    source_type: str
    char_count: int
    excerpt: str = ""
    text: str = ""
    file_size: int = 0
    stored_name: str = ""


class SupplierProfileRead(BaseModel):
    extraction_mode: str = "rules_only"
    confidence: float = 0.0
    vendor_name: str = ""
    company_summary: str = ""
    products_services: str = ""
    data_involvement: str = ""
    security_signals: list[str] = Field(default_factory=list)
    compliance_signals: list[str] = Field(default_factory=list)
    legal_signals: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    missing_materials: list[str] = Field(default_factory=list)
    recommended_focus: str = ""


class ProcurementMaterialGateRead(BaseModel):
    decision: str = "fail"
    relevance_score: float = 0.0
    matched_material_types: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)


class ProcurementRequirementCheckRead(BaseModel):
    key: str
    label: str
    status: str
    required: bool = True
    evidence_titles: list[str] = Field(default_factory=list)
    detail: str = ""


class SupplierDossierRead(BaseModel):
    vendor_name: str = ""
    legal_entity: str = ""
    service_model: str = ""
    source_urls: list[str] = Field(default_factory=list)
    data_access_level: str = "unknown"
    hosting_region: str = ""
    subprocessor_signal: str = "unknown"
    security_signal_summary: list[str] = Field(default_factory=list)


class ProcurementAgentExtractResult(BaseModel):
    vendor_draft: VendorCandidateCreate
    extraction_summary: str
    extracted_materials: list[ProcurementMaterialRead] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    supplier_profile: SupplierProfileRead | None = None
    material_gate: ProcurementMaterialGateRead | None = None
    requirement_checks: list[ProcurementRequirementCheckRead] = Field(default_factory=list)
    supplier_dossier: SupplierDossierRead | None = None


class ProcurementMaterialSessionRead(BaseModel):
    vendor_draft: VendorCandidateCreate
    extraction_summary: str
    extracted_materials: list[ProcurementMaterialRead] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    supplier_profile: SupplierProfileRead | None = None
    material_gate: ProcurementMaterialGateRead | None = None
    requirement_checks: list[ProcurementRequirementCheckRead] = Field(default_factory=list)
    supplier_dossier: SupplierDossierRead | None = None
    focus_points: str = ""


class ProcurementAgentRunRequest(BaseModel):
    focus_points: str = ""
    top_k: int = Field(default=6, ge=1, le=10)


class VendorSelectRequest(BaseModel):
    actor_role: str = "procurement"
    reason: str = ""


class ProjectLegalReviewRequest(BaseModel):
    query: str = ""
    user_role: str = "legal"
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


class StructuredEvidenceRead(BaseModel):
    document_title: str
    location: str
    snippet: str


class StructuredCheckItemRead(BaseModel):
    label: str
    status: str
    detail: str


class RequirementCheckRead(BaseModel):
    key: str
    label: str
    checked: bool
    detail: str


class StructuredReviewRead(BaseModel):
    review_kind: str
    conclusion: str
    recommendation: str
    summary: str
    analysis_tags: list[str] = Field(default_factory=list)
    fit_decision: str = ""
    fit_reason: str = ""
    missing_materials: list[str] = Field(default_factory=list)
    escalation: str = ""
    risk_level: str = "medium"
    decision_suggestion: str = ""
    next_step: str = ""
    legal_handoff_recommendation: str = "hold_for_procurement"
    legal_handoff_reason: str = ""
    clause_gaps: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    check_items: list[StructuredCheckItemRead] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    evidence: list[StructuredEvidenceRead] = Field(default_factory=list)


class VendorCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    vendor_name: str
    source_platform: str
    source_url: str
    contact_name: str
    contact_email: str
    contact_phone: str
    profile_summary: str
    procurement_notes: str
    handles_company_data: bool = False
    requires_system_integration: bool = False
    quoted_amount: float = 0.0
    ai_review_summary: str
    structured_review: StructuredReviewRead | None = None
    ai_recommendation: str
    ai_review_trace_id: str
    manual_decision: str
    manual_reason: str
    status: str
    created_at: datetime
    updated_at: datetime


class ProjectArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    document_id: str
    linked_vendor_id: str
    stage: str
    artifact_type: str
    title: str
    direction: str
    version_no: int
    required: bool
    status: str
    notes: str
    created_at: datetime
    updated_at: datetime


class ProjectArtifactPreviewRead(BaseModel):
    artifact_id: str
    document_id: str
    title: str
    source_title: str = ""
    text_content: str = ""
    content_excerpt: str = ""


class LegalHandoffRead(BaseModel):
    vendor_id: str
    vendor_name: str
    contact_name: str
    contact_email: str
    contact_phone: str
    source_url: str
    our_contract_status: str = "missing"
    our_contract_notes: str = ""
    counterparty_contract_status: str = "missing"
    counterparty_contract_notes: str = ""
    standard_contract_status: str
    standard_contract_notes: str
    vendor_redline_status: str
    vendor_redline_notes: str
    ready_for_legal_review: bool = False


class ProjectRiskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    linked_vendor_id: str
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
    subject_type: str
    subject_id: str
    decision_type: str
    decision_by: str
    ai_recommendation: str
    manual_decision: str
    decision_summary: str
    structured_summary: StructuredReviewRead | None = None
    reason: str
    trace_id: str
    created_at: datetime


class ProjectStageRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    stage: str
    from_stage: str
    to_stage: str
    action: str
    actor_role: str
    reason: str
    status: str
    owner_role: str
    blocking_reason: str
    started_at: datetime
    ended_at: datetime | None


class ProjectArchiveSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    stage: str
    snapshot_json: str
    created_at: datetime


class ProjectSummaryRead(BaseModel):
    id: str
    title: str
    requester_name: str
    department: str
    vendor_name: str
    selected_vendor_id: str
    category: str
    budget_amount: float
    currency: str
    current_stage: str
    risk_level: str
    status: str
    current_owner_role: str
    open_task_count: int
    open_risk_count: int
    vendor_count: int
    created_at: datetime
    updated_at: datetime


class ProjectDetailRead(BaseModel):
    id: str
    title: str
    requester_name: str
    department: str
    vendor_name: str
    selected_vendor_id: str
    category: str
    budget_amount: float
    currency: str
    summary: str
    business_value: str
    target_go_live_date: str
    data_scope: str
    current_stage: str
    risk_level: str
    status: str
    current_owner_role: str
    chat_session_id: str
    draft_editable: bool = False
    allowed_actions: list[str] = Field(default_factory=list)
    application_form_ready: bool = False
    application_form_summary: str = ""
    application_checks: list[RequirementCheckRead] = Field(default_factory=list)
    procurement_material_session: ProcurementMaterialSessionRead | None = None
    latest_legal_review: StructuredReviewRead | None = None
    legal_handoff: LegalHandoffRead | None = None
    blocker_summary: list[str] = Field(default_factory=list)
    tasks: list[ProjectTaskRead] = Field(default_factory=list)
    vendors: list[VendorCandidateRead] = Field(default_factory=list)
    artifacts: list[ProjectArtifactRead] = Field(default_factory=list)
    risks: list[ProjectRiskRead] = Field(default_factory=list)
    decisions: list[ProjectDecisionRead] = Field(default_factory=list)
    stages: list[ProjectStageRecordRead] = Field(default_factory=list)
    archives: list[ProjectArchiveSnapshotRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProjectTimelineEvent(BaseModel):
    kind: str
    stage: str
    title: str
    summary: str
    created_at: datetime
    trace_id: str = ""


class VendorReviewResult(BaseModel):
    project: ProjectDetailRead
    vendor: VendorCandidateRead
    review: QueryResponse
    assessment: StructuredReviewRead
    risks: list[ProjectRiskRead] = Field(default_factory=list)


class ProcurementAgentReviewResult(BaseModel):
    review: QueryResponse
    assessment: StructuredReviewRead
    generated_query: str
    material_gate: ProcurementMaterialGateRead | None = None
    requirement_checks: list[ProcurementRequirementCheckRead] = Field(default_factory=list)
    supplier_dossier: SupplierDossierRead | None = None


class ProcurementAgentRunResult(BaseModel):
    vendor_draft: VendorCandidateCreate
    extraction_summary: str
    extracted_materials: list[ProcurementMaterialRead] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    supplier_profile: SupplierProfileRead | None = None
    review: QueryResponse
    assessment: StructuredReviewRead
    generated_query: str
    material_gate: ProcurementMaterialGateRead | None = None
    requirement_checks: list[ProcurementRequirementCheckRead] = Field(default_factory=list)
    supplier_dossier: SupplierDossierRead | None = None


class ProjectLegalReviewResult(BaseModel):
    project: ProjectDetailRead
    review: QueryResponse
    assessment: StructuredReviewRead
    risks: list[ProjectRiskRead] = Field(default_factory=list)
