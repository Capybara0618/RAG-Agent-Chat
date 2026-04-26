from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Chunk,
    Document,
    ProcurementProject,
    ProcurementStage,
    ProjectArtifact,
    ProjectArchiveSnapshot,
    ProjectRisk,
    ProjectStageRecord,
    ProjectTask,
    VendorCandidate,
    VendorCandidateStatus,
)
from app.repositories.project_repository import ProjectRepository
from app.schemas.auth import UserProfileRead
from app.schemas.chat import QueryRequest, QueryResponse
from app.schemas.common import Citation, ToolCallRead
from app.schemas.project import (
    ProcurementAgentExtractResult,
    ProcurementAgentRunResult,
    ProcurementMaterialGateRead,
    ProcurementMaterialRead,
    ProcurementMaterialSessionRead,
    ProcurementAgentReviewRequest,
    ProcurementAgentReviewResult,
    ProcurementRequirementCheckRead,
    LegalHandoffRead,
    ProjectArchiveSnapshotRead,
    ProjectArtifactCreate,
    ProjectArtifactPreviewRead,
    ProjectArtifactRead,
    ProjectArtifactUpdate,
    ProjectCancelRequest,
    ProjectCreate,
    ProjectDecisionRead,
    ProjectDetailRead,
    ProjectFinalApproveRequest,
    ProjectFinalReturnRequest,
    ProjectLegalDecisionRequest,
    ProjectLegalReviewRequest,
    ProjectLegalReviewResult,
    ProjectManagerDecisionRequest,
    ProjectRiskRead,
    ProjectSignRequest,
    ProjectStageRecordRead,
    ProjectSubmitRequest,
    ProjectSummaryRead,
    ProjectTaskCreate,
    ProjectTaskRead,
    ProjectTaskUpdate,
    ProjectTimelineEvent,
    ProjectUpdate,
    ProjectWithdrawRequest,
    RequirementCheckRead,
    SupplierDossierRead,
    SupplierProfileRead,
    StructuredCheckItemRead,
    StructuredEvidenceRead,
    StructuredReviewRead,
    VendorCandidateCreate,
    VendorCandidateRead,
    VendorReviewRequest,
    VendorReviewResult,
    VendorSelectRequest,
)
from app.services.agent.service import KnowledgeOpsAgentService
from app.services.ingestion.connectors import DocumentParser
from app.services.retrieval.embeddings import tokenize_text


@dataclass(frozen=True)
class StageBlueprint:
    stage: ProcurementStage
    owner_role: str
    required_tasks: list[tuple[str, str, str]]
    required_artifacts: list[tuple[str, str, str]]


@dataclass(frozen=True)
class ProcurementAgentVendorDraft:
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
    ai_recommendation: str = ""


@dataclass(frozen=True)
class ProcurementMaterialText:
    name: str
    source_type: str
    text: str
    file_size: int = 0
    stored_name: str = ""


@dataclass(frozen=True)
class SupplierProfileInsights:
    extraction_mode: str = "rules_only"
    confidence: float = 0.0
    vendor_name: str = ""
    company_summary: str = ""
    products_services: str = ""
    data_involvement: str = ""
    security_signals: tuple[str, ...] = ()
    compliance_signals: tuple[str, ...] = ()
    legal_signals: tuple[str, ...] = ()
    source_urls: tuple[str, ...] = ()
    missing_materials: tuple[str, ...] = ()
    recommended_focus: str = ""


@dataclass(frozen=True)
class ProcurementMaterialGate:
    decision: str = "fail"
    relevance_score: float = 0.0
    matched_material_types: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProcurementRequirementCheck:
    key: str
    label: str
    status: str
    required: bool = True
    evidence_titles: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class SupplierDossier:
    vendor_name: str = ""
    legal_entity: str = ""
    service_model: str = ""
    source_urls: tuple[str, ...] = ()
    data_access_level: str = "unknown"
    hosting_region: str = ""
    subprocessor_signal: str = "unknown"
    security_signal_summary: tuple[str, ...] = ()


class ProjectService:
    STAGE_ORDER = [
        ProcurementStage.business_draft.value,
        ProcurementStage.manager_review.value,
        ProcurementStage.procurement_sourcing.value,
        ProcurementStage.legal_review.value,
        ProcurementStage.signing.value,
        ProcurementStage.completed.value,
    ]

    LEGAL_OUR_CONTRACT_ARTIFACT_TYPES = ("our_procurement_contract", "standard_contract_dispatch")
    LEGAL_COUNTERPARTY_CONTRACT_ARTIFACT_TYPES = ("counterparty_redline_contract", "vendor_redline_contract")
    LEGAL_DEFAULT_REVIEW_QUERY = (
        "请对比我方采购合同与对方修改后的采购合同，聚焦责任限制、赔偿或违约责任、解约条件、保密义务、"
        "争议解决与适用法律等核心红线，输出结构化结论、问题条款、建议动作，并给出引用依据。"
    )
    LEGAL_CONCERN_DESCRIPTIONS = {
        "责任上限": "整体赔付范围被明显压缩",
        "赔偿责任": "违约或侵权后的赔付责任被明显缩小",
        "审计权": "我方对供应商的核查与监督能力被削弱",
        "数据处理": "数据使用、存放或传输边界被放宽",
        "保密义务": "保密信息对外共享限制被放松",
        "安全事件通知": "安全事件通报时限从固定要求变成模糊表述",
        "分包限制": "供应商可自行引入第三方或子处理方",
        "便利终止": "我方提前退出合同的权利被压缩",
        "付款条款": "付款安排前置或预付款比例偏高",
        "服务水平": "量化服务承诺被改成尽力而为",
        "争议解决与适用法律": "适用法律或争议解决地点偏向境外",
    }

    STAGE_BLUEPRINTS = {
        ProcurementStage.business_draft.value: StageBlueprint(
            stage=ProcurementStage.business_draft,
            owner_role="business",
            required_tasks=[
                ("intake", "填写并确认采购申请表", "business"),
            ],
            required_artifacts=[
                ("procurement_application_form", "采购申请表", "internal"),
            ],
        ),
        ProcurementStage.manager_review.value: StageBlueprint(
            stage=ProcurementStage.manager_review,
            owner_role="manager",
            required_tasks=[
                ("review", "审查采购必要性与内部替代方案", "manager"),
                ("review", "确认预算与立项是否合理", "manager"),
            ],
            required_artifacts=[
                ("manager_review_note", "上级审批意见", "internal"),
            ],
        ),
        ProcurementStage.procurement_sourcing.value: StageBlueprint(
            stage=ProcurementStage.procurement_sourcing,
            owner_role="procurement",
            required_tasks=[
                ("sourcing", "收集候选供应商资料", "procurement"),
                ("sourcing", "完成候选供应商比选", "procurement"),
                ("selection", "选择目标供应商", "procurement"),
            ],
            required_artifacts=[
                ("vendor_comparison_sheet", "候选供应商比选表", "internal"),
                ("procurement_recommendation", "采购建议说明", "internal"),
            ],
        ),
        ProcurementStage.legal_review.value: StageBlueprint(
            stage=ProcurementStage.legal_review,
            owner_role="legal",
            required_tasks=[
                ("review", "完成法务审查并给出结论", "legal"),
            ],
            required_artifacts=[
                ("our_procurement_contract", "我方采购合同", "internal"),
                ("counterparty_redline_contract", "对方修改后的采购合同", "inbound"),
            ],
        ),
        ProcurementStage.final_approval.value: StageBlueprint(
            stage=ProcurementStage.final_approval,
            owner_role="manager",
            required_tasks=[
                ("approval", "完成终审审批并确认项目落地", "executive"),
            ],
            required_artifacts=[
                ("approval_package", "终审材料包", "internal"),
            ],
        ),
        ProcurementStage.signing.value: StageBlueprint(
            stage=ProcurementStage.signing,
            owner_role="admin",
            required_tasks=[
                ("execution", "完成签署并整理归档材料", "operations"),
            ],
            required_artifacts=[
                ("signed_contract", "已签署合同", "internal"),
                ("archive_summary", "归档摘要", "internal"),
            ],
        ),
    }

    def __init__(
        self,
        *,
        repository: ProjectRepository,
        agent_service: KnowledgeOpsAgentService,
        storage_dir: Path | str | None = None,
    ) -> None:
        self.repository = repository
        self.agent_service = agent_service
        base_storage_dir = Path(storage_dir) if storage_dir is not None else Path("data/uploads")
        self.procurement_material_dir = base_storage_dir / "procurement_materials"
        self.procurement_material_dir.mkdir(parents=True, exist_ok=True)

    def create_project(self, db: Session, payload: ProjectCreate, *, created_by_user_id: str = "") -> ProjectDetailRead:
        project = self.repository.create_project(
            db,
            created_by_user_id=created_by_user_id,
            title=payload.title,
            requester_name=payload.requester_name,
            department=payload.department,
            vendor_name=payload.vendor_name,
            category=payload.category,
            budget_amount=payload.budget_amount,
            currency=payload.currency,
            summary=payload.summary,
            business_value=payload.business_value,
            target_go_live_date=payload.target_go_live_date,
            data_scope=payload.data_scope,
        )
        self.repository.create_stage_record(
            db,
            project_id=project.id,
            stage=ProcurementStage.business_draft.value,
            from_stage="",
            to_stage=ProcurementStage.business_draft.value,
            action="create",
            actor_role="business",
            reason="",
            status="active",
            owner_role=self.STAGE_BLUEPRINTS[ProcurementStage.business_draft.value].owner_role,
        )
        self._ensure_stage_defaults(db, project, ProcurementStage.business_draft.value)
        self._sync_business_draft_form_state(db, project)
        if payload.vendor_name:
            self.repository.create_vendor_candidate(
                db,
                project_id=project.id,
                vendor_name=payload.vendor_name,
                source_platform="business_input",
                source_url="",
                contact_name="",
                contact_email="",
                contact_phone="",
                profile_summary=payload.summary,
                procurement_notes="业务发起时录入的候选供应商。",
                handles_company_data=bool(payload.data_scope and payload.data_scope != "none"),
                requires_system_integration=payload.category in {"software", "customer-support-saas"},
                quoted_amount=float(payload.budget_amount or 0),
            )
        self._refresh_active_stage_blocking_reason(db, project)
        db.commit()
        return self.get_project_detail(db, project.id)

    def create_demo_project(self, db: Session, *, created_by_user_id: str = "") -> ProjectDetailRead:
        detail = self.create_project(
            db,
            ProjectCreate(
                title="AlphaDesk 客服 SaaS 采购项目",
                requester_name="王悦",
                department="客户服务部",
                vendor_name="AlphaDesk",
                category="customer-support-saas",
                budget_amount=1200000,
                currency="CNY",
                summary="客户服务部计划采购在线客服与工单协同 SaaS。供应商将处理客户聊天记录与工单附件，因此需要经过业务申请、上级审批、采购筛选、法务审查与签署归档。",
                business_value="统一客服流程，缩短响应时长，并提升客户服务质量。",
                target_go_live_date="2026-06-30",
                data_scope="customer_data",
            ),
            created_by_user_id=created_by_user_id,
        )
        project = self._require_project(db, detail.id)
        existing_names = {vendor.vendor_name for vendor in self.repository.list_vendor_candidates(db, project.id)}
        if "ServiceNova" not in existing_names:
            self.repository.create_vendor_candidate(
                db,
                project_id=project.id,
                vendor_name="ServiceNova",
                source_platform="1688",
                source_url="https://example.com/service-nova",
                contact_name="",
                contact_email="servicenova@example.com",
                contact_phone="400-800-9000",
                profile_summary="备选 SaaS 供应商，价格更低但合同条款较弱。",
                procurement_notes="演示项目中附带的备选供应商。",
                handles_company_data=True,
                requires_system_integration=True,
                quoted_amount=980000,
            )
        db.commit()
        return self.get_project_detail(db, detail.id)

    def list_projects(self, db: Session) -> list[ProjectSummaryRead]:
        summaries: list[ProjectSummaryRead] = []
        for project in self.repository.list_projects(db):
            summaries.append(self._serialize_summary(db, project))
        return summaries

    def list_projects_for_user(self, db: Session, current_user: UserProfileRead) -> list[ProjectSummaryRead]:
        return [
            self._redact_summary_for_user(self._serialize_summary(db, project), current_user)
            for project in self.repository.list_projects(db)
            if self._can_view_project(db, current_user, project)
        ]

    def get_project_detail(self, db: Session, project_id: str) -> ProjectDetailRead:
        project = self._require_project(db, project_id)
        self._normalize_optional_approval_stage_requirements(db, project, project.current_stage)
        self._ensure_stage_defaults(db, project, project.current_stage)
        if project.current_stage == ProcurementStage.final_approval.value:
            # Legacy projects may still be parked in final_approval. Pre-create signing tasks/artifacts
            # so admins can finish them from the streamlined signing workspace.
            self._ensure_stage_defaults(db, project, ProcurementStage.signing.value)
        self._sync_business_draft_form_state(db, project)
        if project.current_stage == ProcurementStage.legal_review.value and project.selected_vendor_id:
            try:
                selected_vendor = self._require_selected_vendor(db, project)
            except ValueError:
                selected_vendor = None
            if selected_vendor is not None:
                self._sync_legal_review_handoff_state(db, project, selected_vendor)
        db.commit()
        db.refresh(project)
        tasks = self.repository.list_tasks(db, project.id)
        vendors = self.repository.list_vendor_candidates(db, project.id)
        artifacts = self.repository.list_artifacts(db, project.id)
        risks = self.repository.list_risks(db, project.id)
        decisions = self.repository.list_decisions(db, project.id)
        stages = self.repository.list_stage_records(db, project.id)
        archives = self.repository.list_archive_snapshots(db, project.id)
        blockers = self._collect_blockers(project, tasks, artifacts, vendors, project.current_stage)
        return self._serialize_detail(project, tasks, vendors, artifacts, risks, decisions, stages, archives, blockers)

    def get_project_detail_for_user(self, db: Session, project_id: str, current_user: UserProfileRead) -> ProjectDetailRead:
        project = self._require_project(db, project_id)
        if not self._can_view_project(db, current_user, project):
            raise PermissionError("Project is not visible to the current account.")
        return self._redact_detail_for_user(self.get_project_detail(db, project_id), current_user)

    def update_project(self, db: Session, project_id: str, payload: ProjectUpdate) -> ProjectDetailRead:
        project = self._require_project(db, project_id)
        if project.current_stage != ProcurementStage.business_draft.value or project.status != "active":
            raise ValueError("Project basic information can only be edited in active business draft stage.")

        for field_name in (
            "title",
            "requester_name",
            "department",
            "vendor_name",
            "category",
            "budget_amount",
            "currency",
            "summary",
            "business_value",
            "target_go_live_date",
            "data_scope",
        ):
            value = getattr(payload, field_name)
            if value is not None:
                setattr(project, field_name, value)

        self._sync_business_input_vendor(db, project)
        self._sync_business_draft_form_state(db, project)
        self._record_manual_decision(
            db,
            project=project,
            subject_type="project",
            subject_id=project.id,
            decision_type="draft_update",
            decision_by="business",
            manual_decision="updated",
            summary="业务申请草稿已更新。",
            reason="",
        )
        self._refresh_active_stage_blocking_reason(db, project)
        db.commit()
        return self.get_project_detail(db, project.id)

    def submit_project(self, db: Session, project_id: str, payload: ProjectSubmitRequest) -> ProjectDetailRead:
        project = self._require_project(db, project_id)
        self._require_stage(project, ProcurementStage.business_draft.value)
        self._ensure_stage_ready_to_leave(db, project, ProcurementStage.business_draft.value)
        self._record_manual_decision(
            db,
            project=project,
            subject_type="project",
            subject_id=project.id,
            decision_type="submit",
            decision_by=payload.actor_role,
            manual_decision="submitted",
            summary="业务申请已提交，进入上级审批。",
            reason=payload.reason,
        )
        self._move_project_to_stage(
            db,
            project=project,
            target_stage=ProcurementStage.manager_review.value,
            action="submit",
            actor_role=payload.actor_role,
            reason=payload.reason,
        )
        db.commit()
        return self.get_project_detail(db, project.id)

    def withdraw_project(self, db: Session, project_id: str, payload: ProjectWithdrawRequest) -> ProjectDetailRead:
        project = self._require_project(db, project_id)
        if project.current_stage not in {ProcurementStage.business_draft.value, ProcurementStage.manager_review.value}:
            raise ValueError("Project can only be withdrawn before manager approval.")
        self._record_manual_decision(
            db,
            project=project,
            subject_type="project",
            subject_id=project.id,
            decision_type="withdraw",
            decision_by=payload.actor_role,
            manual_decision="withdrawn",
            summary="业务申请已撤回到草稿。",
            reason=payload.reason,
        )
        if project.current_stage != ProcurementStage.business_draft.value:
            self._move_project_to_stage(
                db,
                project=project,
                target_stage=ProcurementStage.business_draft.value,
                action="withdraw",
                actor_role=payload.actor_role,
                reason=payload.reason,
            )
        else:
            self._refresh_active_stage_blocking_reason(db, project)
        db.commit()
        return self.get_project_detail(db, project.id)

    def manager_decision(self, db: Session, project_id: str, payload: ProjectManagerDecisionRequest) -> ProjectDetailRead:
        project = self._require_project(db, project_id)
        self._require_stage(project, ProcurementStage.manager_review.value)
        self._normalize_optional_approval_stage_requirements(db, project, ProcurementStage.manager_review.value)
        if payload.decision == "approve":
            self._ensure_stage_ready_to_leave(db, project, ProcurementStage.manager_review.value)
            self._record_manual_decision(
                db,
                project=project,
                subject_type="project",
                subject_id=project.id,
                decision_type="manager_review",
                decision_by=payload.actor_role,
                manual_decision="approved",
                summary="上级审批通过，进入采购筛选。",
                reason=payload.reason,
            )
            self._move_project_to_stage(
                db,
                project=project,
                target_stage=ProcurementStage.procurement_sourcing.value,
                action="manager_approve",
                actor_role=payload.actor_role,
                reason=payload.reason,
            )
        else:
            if not payload.reason.strip():
                raise ValueError("Manager return reason is required.")
            self._record_manual_decision(
                db,
                project=project,
                subject_type="project",
                subject_id=project.id,
                decision_type="manager_review",
                decision_by=payload.actor_role,
                manual_decision="returned",
                summary="上级审批退回草稿。",
                reason=payload.reason,
            )
            self._move_project_to_stage(
                db,
                project=project,
                target_stage=ProcurementStage.business_draft.value,
                action="manager_return",
                actor_role=payload.actor_role,
                reason=payload.reason,
            )
        db.commit()
        return self.get_project_detail(db, project.id)

    def create_task(self, db: Session, project_id: str, payload: ProjectTaskCreate) -> ProjectTaskRead:
        project = self._require_project(db, project_id)
        task = self.repository.create_task(
            db,
            project_id=project.id,
            stage=payload.stage,
            task_type=payload.task_type,
            title=payload.title,
            details=payload.details,
            assignee_role=payload.assignee_role,
            required=payload.required,
        )
        self._refresh_active_stage_blocking_reason(db, project)
        db.commit()
        return ProjectTaskRead.model_validate(task)

    def update_task(self, db: Session, project_id: str, task_id: str, payload: ProjectTaskUpdate) -> ProjectTaskRead:
        project = self._require_project(db, project_id)
        task = self.repository.get_task(db, task_id)
        if task is None or task.project_id != project_id:
            raise ValueError("Project task not found.")
        task.status = payload.status
        self._refresh_active_stage_blocking_reason(db, project)
        db.commit()
        db.refresh(task)
        return ProjectTaskRead.model_validate(task)

    def create_vendor_candidate(self, db: Session, project_id: str, payload: VendorCandidateCreate) -> VendorCandidateRead:
        project = self._require_project(db, project_id)
        self._require_stage(project, ProcurementStage.procurement_sourcing.value)
        candidate = self.repository.create_vendor_candidate(
            db,
            project_id=project.id,
            vendor_name=payload.vendor_name,
            source_platform=payload.source_platform,
            source_url=payload.source_url,
            contact_name=payload.contact_name,
            contact_email=payload.contact_email,
            contact_phone=payload.contact_phone,
            profile_summary=payload.profile_summary,
            procurement_notes=payload.procurement_notes,
            handles_company_data=payload.handles_company_data,
            requires_system_integration=payload.requires_system_integration,
            quoted_amount=float(payload.quoted_amount or 0),
        )
        self._refresh_active_stage_blocking_reason(db, project)
        db.commit()
        return VendorCandidateRead.model_validate(candidate)

    def review_vendor(self, db: Session, project_id: str, vendor_id: str, payload: VendorReviewRequest) -> VendorReviewResult:
        project = self._require_project(db, project_id)
        self._require_stage(project, ProcurementStage.procurement_sourcing.value)
        vendor = self._require_vendor(db, project.id, vendor_id)
        review = self.agent_service.query(
            db,
            QueryRequest(
                query=payload.query,
                session_id=project.chat_session_id or None,
                user_role=payload.user_role,
                top_k=payload.top_k,
                task_mode="procurement_fit_review",
            ),
            current_user=UserProfileRead(
                id=f"project-{payload.user_role}",
                username=f"project-{payload.user_role}",
                display_name=f"Project {payload.user_role}",
                role=payload.user_role,
                department=project.department,
                status="active",
            ),
        )
        self._ensure_review_trace_id(review)
        project.chat_session_id = review.session_id
        vendor.ai_review_summary = review.answer
        vendor.ai_recommendation = self._derive_ai_recommendation(review.next_action, review.debug_summary)
        vendor.ai_review_trace_id = review.trace_id
        structured_review = self._build_vendor_structured_review(project, vendor, review)
        vendor.ai_review_json = json.dumps(structured_review.model_dump(), ensure_ascii=False)
        self.repository.create_decision(
            db,
            project_id=project.id,
            stage=project.current_stage,
            subject_type="vendor",
            subject_id=vendor.id,
            decision_type="vendor_ai_review",
            decision_by="system",
            ai_recommendation=vendor.ai_recommendation,
            manual_decision="",
            decision_summary=review.answer,
            structured_summary_json=json.dumps(structured_review.model_dump(), ensure_ascii=False),
            reason="",
            trace_id=review.trace_id,
        )
        self.repository.clear_stage_risks(db, project.id, project.current_stage, linked_vendor_id=vendor.id)
        risks = self._materialize_risks(db, project, review, linked_vendor_id=vendor.id)
        project.risk_level = self._derive_risk_level(risks, review.next_action)
        self._refresh_active_stage_blocking_reason(db, project)
        db.commit()
        return VendorReviewResult(
            project=self.get_project_detail(db, project.id),
            vendor=self._serialize_vendor(self._require_vendor(db, project.id, vendor.id)),
            review=review,
            assessment=structured_review,
            risks=[ProjectRiskRead.model_validate(risk) for risk in risks],
        )

    def extract_procurement_vendor_materials(
        self,
        db: Session,
        project_id: str,
        *,
        uploaded_files: list[tuple[str, bytes]],
        current_user: UserProfileRead,
    ) -> ProcurementAgentExtractResult:
        project = self._require_project(db, project_id)
        self._require_stage(project, ProcurementStage.procurement_sourcing.value)
        stored_names = self._store_procurement_material_uploads(project.id, uploaded_files)
        materials = self._parse_procurement_materials(uploaded_files, stored_names=stored_names)
        draft, summary, warnings, supplier_profile = self._extract_vendor_draft_from_materials(project, materials, current_user)
        material_gate, requirement_checks, supplier_dossier = self._prepare_procurement_review_inputs(
            project=project,
            materials=materials,
            draft=draft,
            supplier_profile=supplier_profile,
        )
        result = ProcurementAgentExtractResult(
            vendor_draft=self._serialize_vendor_draft(draft),
            extraction_summary=summary,
            extracted_materials=self._serialize_procurement_materials(materials),
            warnings=warnings,
            supplier_profile=self._serialize_supplier_profile(supplier_profile),
            material_gate=self._serialize_material_gate(material_gate),
            requirement_checks=self._serialize_requirement_checks(requirement_checks),
            supplier_dossier=self._serialize_supplier_dossier(supplier_dossier),
        )
        self._persist_procurement_material_session(
            project,
            vendor_draft=result.vendor_draft,
            extracted_materials=result.extracted_materials,
            extraction_summary=summary,
            warnings=warnings,
            supplier_profile=result.supplier_profile,
            material_gate=result.material_gate,
            requirement_checks=result.requirement_checks,
            supplier_dossier=result.supplier_dossier,
            focus_points="",
        )
        db.commit()
        return result

    def procurement_agent_run_from_materials(
        self,
        db: Session,
        project_id: str,
        *,
        uploaded_files: list[tuple[str, bytes]],
        focus_points: str,
        top_k: int,
        current_user: UserProfileRead,
    ) -> ProcurementAgentRunResult:
        project = self._require_project(db, project_id)
        self._require_stage(project, ProcurementStage.procurement_sourcing.value)
        stored_names = self._store_procurement_material_uploads(project.id, uploaded_files)
        materials = self._parse_procurement_materials(uploaded_files, stored_names=stored_names)
        draft, summary, warnings, supplier_profile = self._extract_vendor_draft_from_materials(project, materials, current_user)
        material_gate, requirement_checks, supplier_dossier = self._prepare_procurement_review_inputs(
            project=project,
            materials=materials,
            draft=draft,
            supplier_profile=supplier_profile,
        )
        review, assessment, generated_query = self._run_procurement_agent_review(
            db,
            project=project,
            materials=materials,
            draft=draft,
            focus_points=focus_points,
            top_k=top_k,
            current_user=current_user,
            supplier_profile=supplier_profile,
            material_gate=material_gate,
            requirement_checks=requirement_checks,
            supplier_dossier=supplier_dossier,
        )
        result = ProcurementAgentRunResult(
            vendor_draft=self._serialize_vendor_draft(draft),
            extraction_summary=summary,
            extracted_materials=self._serialize_procurement_materials(materials),
            warnings=warnings,
            supplier_profile=self._serialize_supplier_profile(supplier_profile),
            review=review,
            assessment=assessment,
            generated_query=generated_query,
            material_gate=self._serialize_material_gate(material_gate),
            requirement_checks=self._serialize_requirement_checks(requirement_checks),
            supplier_dossier=self._serialize_supplier_dossier(supplier_dossier),
        )
        self._persist_procurement_material_session(
            project,
            vendor_draft=result.vendor_draft,
            extracted_materials=result.extracted_materials,
            extraction_summary=summary,
            warnings=warnings,
            supplier_profile=result.supplier_profile,
            material_gate=result.material_gate,
            requirement_checks=result.requirement_checks,
            supplier_dossier=result.supplier_dossier,
            focus_points=focus_points,
        )
        db.commit()
        return result

    def procurement_agent_review(
        self,
        db: Session,
        project_id: str,
        payload: ProcurementAgentReviewRequest,
        *,
        current_user: UserProfileRead,
    ) -> ProcurementAgentReviewResult:
        project = self._require_project(db, project_id)
        self._require_stage(project, ProcurementStage.procurement_sourcing.value)
        existing_session = self._procurement_material_session_from_json(project.procurement_materials_json)
        supplier_profile = payload.supplier_profile
        if supplier_profile is None and existing_session is not None:
            supplier_profile = existing_session.supplier_profile
        draft = ProcurementAgentVendorDraft(
            vendor_name=payload.vendor_name.strip(),
            source_platform=payload.source_platform.strip(),
            source_url=payload.source_url.strip(),
            contact_name=payload.contact_name.strip(),
            contact_email=payload.contact_email.strip(),
            contact_phone=payload.contact_phone.strip(),
            profile_summary=payload.profile_summary.strip(),
            procurement_notes=payload.procurement_notes.strip(),
            handles_company_data=bool(payload.handles_company_data),
            requires_system_integration=bool(payload.requires_system_integration),
            quoted_amount=float(payload.quoted_amount or 0),
        )
        existing_materials = self._materials_from_reads(existing_session.extracted_materials) if existing_session is not None else []
        if not existing_materials:
            existing_materials = self._build_procurement_form_materials(project, draft)
        material_gate, requirement_checks, supplier_dossier = self._prepare_procurement_review_inputs(
            project=project,
            materials=existing_materials,
            draft=draft,
            supplier_profile=self._supplier_profile_insights_from_read(supplier_profile),
        )
        review, assessment, generated_query = self._run_procurement_agent_review(
            db,
            project=project,
            materials=existing_materials,
            draft=draft,
            focus_points=payload.focus_points,
            top_k=payload.top_k,
            current_user=current_user,
            supplier_profile=self._supplier_profile_insights_from_read(supplier_profile),
            material_gate=material_gate,
            requirement_checks=requirement_checks,
            supplier_dossier=supplier_dossier,
        )
        if existing_session is not None:
            self._persist_procurement_material_session(
                project,
                vendor_draft=self._serialize_vendor_draft(draft),
                extracted_materials=existing_session.extracted_materials,
                extraction_summary=existing_session.extraction_summary,
                warnings=existing_session.warnings,
                supplier_profile=supplier_profile,
                material_gate=self._serialize_material_gate(material_gate),
                requirement_checks=self._serialize_requirement_checks(requirement_checks),
                supplier_dossier=self._serialize_supplier_dossier(supplier_dossier),
                focus_points=payload.focus_points,
            )
            db.commit()
        return ProcurementAgentReviewResult(
            review=review,
            assessment=assessment,
            generated_query=generated_query,
            material_gate=self._serialize_material_gate(material_gate),
            requirement_checks=self._serialize_requirement_checks(requirement_checks),
            supplier_dossier=self._serialize_supplier_dossier(supplier_dossier),
        )

    def _build_procurement_form_materials(
        self,
        project: ProcurementProject,
        draft: ProcurementAgentVendorDraft,
    ) -> list[ProcurementMaterialText]:
        lines = [
            f"供应商名称：{draft.vendor_name or '未提供'}",
            f"来源平台：{draft.source_platform or '未提供'}",
            f"官网或公开来源：{draft.source_url or '未提供'}",
            f"联系邮箱：{draft.contact_email or '未提供'}",
            f"联系姓名：{draft.contact_name or '未提供'}",
            f"联系电话：{draft.contact_phone or '未提供'}",
            f"产品介绍：{draft.profile_summary or '未提供'}",
            f"采购说明：{draft.procurement_notes or '未提供'}",
            f"报价：{draft.quoted_amount:.2f} {project.currency}",
            f"是否处理公司或客户数据：{'是' if draft.handles_company_data else '否'}",
            f"是否需要系统对接：{'是' if draft.requires_system_integration else '否'}",
        ]
        if draft.handles_company_data:
            lines.append("供应商将接触公司或客户业务数据，需要进一步确认数据边界。")
        if draft.requires_system_integration:
            lines.append("供应商需要与内部系统进行对接，后续需进一步确认接口与权限影响。")
        text = "\n".join(lines).strip()
        return [
            ProcurementMaterialText(
                name="structured_vendor_profile.txt",
                source_type="form",
                text=text,
            )
        ]

    def _parse_procurement_materials(
        self,
        uploaded_files: list[tuple[str, bytes]],
        *,
        stored_names: list[str] | None = None,
    ) -> list[ProcurementMaterialText]:
        if not uploaded_files:
            raise ValueError("Please upload at least one supplier material file.")

        parser = DocumentParser()
        materials: list[ProcurementMaterialText] = []
        for index, (file_name, content) in enumerate(uploaded_files):
            if not file_name or not content:
                continue
            source_type, sections = parser.parse_bytes(name=file_name, data=content)
            text_parts: list[str] = []
            for section in sections:
                if section.heading and section.heading not in {file_name, "DOCX"}:
                    text_parts.append(section.heading)
                if section.content.strip():
                    text_parts.append(section.content)
            combined_text = "\n".join(text_parts).strip()
            if not combined_text:
                continue
            materials.append(
                ProcurementMaterialText(
                    name=file_name,
                    source_type=source_type,
                    text=combined_text,
                    file_size=len(content),
                    stored_name=stored_names[index] if stored_names and index < len(stored_names) else "",
                )
            )

        if not materials:
            raise ValueError("Uploaded files could not be parsed into usable supplier text.")
        return materials

    def _store_procurement_material_uploads(self, project_id: str, uploaded_files: list[tuple[str, bytes]]) -> list[str]:
        project_dir = self.procurement_material_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        stored_names: list[str] = []
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        for index, (file_name, content) in enumerate(uploaded_files, start=1):
            safe_name = Path(file_name or f"material_{index}.bin").name
            safe_name = re.sub(r"[^0-9A-Za-z._-]+", "_", safe_name).strip("._") or f"material_{index}.bin"
            stored_name = f"{timestamp}_{uuid.uuid4().hex[:8]}_{safe_name}"
            (project_dir / stored_name).write_bytes(content)
            stored_names.append(stored_name)
        return stored_names

    def _serialize_vendor_draft(self, draft: ProcurementAgentVendorDraft) -> VendorCandidateCreate:
        return VendorCandidateCreate(
            vendor_name=draft.vendor_name,
            source_platform=draft.source_platform,
            source_url=draft.source_url,
            contact_name=draft.contact_name,
            contact_email=draft.contact_email,
            contact_phone=draft.contact_phone,
            profile_summary=draft.profile_summary,
            procurement_notes=draft.procurement_notes,
            handles_company_data=draft.handles_company_data,
            requires_system_integration=draft.requires_system_integration,
            quoted_amount=draft.quoted_amount,
        )

    def _serialize_procurement_materials(self, materials: list[ProcurementMaterialText]) -> list[ProcurementMaterialRead]:
        return [
            ProcurementMaterialRead(
                name=item.name,
                source_type=item.source_type,
                char_count=len(item.text),
                excerpt=item.text[:180],
                text=item.text,
                file_size=item.file_size,
                stored_name=item.stored_name,
            )
            for item in materials
        ]

    def _materials_from_reads(self, materials: list[ProcurementMaterialRead]) -> list[ProcurementMaterialText]:
        return [
            ProcurementMaterialText(
                name=item.name,
                source_type=item.source_type,
                text=item.text,
                file_size=item.file_size,
                stored_name=item.stored_name,
            )
            for item in materials
        ]

    def _supplier_profile_insights_from_read(
        self,
        supplier_profile: SupplierProfileRead | None,
    ) -> SupplierProfileInsights | None:
        if supplier_profile is None:
            return None
        return SupplierProfileInsights(
            extraction_mode=supplier_profile.extraction_mode,
            confidence=supplier_profile.confidence,
            vendor_name=supplier_profile.vendor_name,
            company_summary=supplier_profile.company_summary,
            products_services=supplier_profile.products_services,
            data_involvement=supplier_profile.data_involvement,
            security_signals=tuple(supplier_profile.security_signals),
            compliance_signals=tuple(supplier_profile.compliance_signals),
            legal_signals=tuple(supplier_profile.legal_signals),
            source_urls=tuple(supplier_profile.source_urls),
            missing_materials=tuple(supplier_profile.missing_materials),
            recommended_focus=supplier_profile.recommended_focus,
        )

    def _serialize_material_gate(self, gate: ProcurementMaterialGate | None) -> ProcurementMaterialGateRead | None:
        if gate is None:
            return None
        return ProcurementMaterialGateRead(
            decision=gate.decision,
            relevance_score=gate.relevance_score,
            matched_material_types=list(gate.matched_material_types),
            blocking_reasons=list(gate.blocking_reasons),
        )

    def _serialize_requirement_checks(
        self,
        checks: list[ProcurementRequirementCheck],
    ) -> list[ProcurementRequirementCheckRead]:
        return [
            ProcurementRequirementCheckRead(
                key=item.key,
                label=item.label,
                status=item.status,
                required=item.required,
                evidence_titles=list(item.evidence_titles),
                detail=item.detail,
            )
            for item in checks
        ]

    def _serialize_supplier_dossier(self, dossier: SupplierDossier | None) -> SupplierDossierRead | None:
        if dossier is None:
            return None
        return SupplierDossierRead(
            vendor_name=dossier.vendor_name,
            legal_entity=dossier.legal_entity,
            service_model=dossier.service_model,
            source_urls=list(dossier.source_urls),
            data_access_level=dossier.data_access_level,
            hosting_region=dossier.hosting_region,
            subprocessor_signal=dossier.subprocessor_signal,
            security_signal_summary=list(dossier.security_signal_summary),
        )

    def _persist_procurement_material_session(
        self,
        project: ProcurementProject,
        *,
        vendor_draft: VendorCandidateCreate,
        extracted_materials: list[ProcurementMaterialRead],
        extraction_summary: str,
        warnings: list[str],
        supplier_profile: SupplierProfileRead | None,
        material_gate: ProcurementMaterialGateRead | None,
        requirement_checks: list[ProcurementRequirementCheckRead],
        supplier_dossier: SupplierDossierRead | None,
        focus_points: str,
    ) -> None:
        session = ProcurementMaterialSessionRead(
            vendor_draft=vendor_draft,
            extraction_summary=extraction_summary,
            extracted_materials=extracted_materials,
            warnings=warnings,
            supplier_profile=supplier_profile,
            material_gate=material_gate,
            requirement_checks=requirement_checks,
            supplier_dossier=supplier_dossier,
            focus_points=focus_points,
        )
        project.procurement_materials_json = json.dumps(session.model_dump(), ensure_ascii=False)

    def _procurement_material_session_from_json(self, raw_json: str) -> ProcurementMaterialSessionRead | None:
        if not raw_json or raw_json == "{}":
            return None
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            return None
        try:
            return ProcurementMaterialSessionRead.model_validate(payload)
        except Exception:
            return None

    def _run_procurement_agent_review(
        self,
        db: Session,
        *,
        project: ProcurementProject,
        materials: list[ProcurementMaterialText],
        draft: ProcurementAgentVendorDraft,
        focus_points: str,
        top_k: int,
        current_user: UserProfileRead,
        supplier_profile: SupplierProfileInsights | None = None,
        material_gate: ProcurementMaterialGate,
        requirement_checks: list[ProcurementRequirementCheck],
        supplier_dossier: SupplierDossier,
    ):
        self._validate_procurement_agent_draft(draft)
        recommended_action = self._derive_procurement_precheck_recommendation(material_gate, requirement_checks)
        if recommended_action == "reject_irrelevant_materials":
            generated_query = self._build_procurement_agent_query(
                project,
                draft,
                focus_points,
                supplier_profile=supplier_profile,
                supplier_dossier=supplier_dossier,
                requirement_checks=requirement_checks,
            )
            review = self._build_procurement_precheck_review(
                project=project,
                draft=draft,
                material_gate=material_gate,
                requirement_checks=requirement_checks,
                supplier_dossier=supplier_dossier,
                supplier_profile=supplier_profile,
            )
            review = self._attach_procurement_precheck_evidence(
                db,
                review=review,
                query=generated_query,
                user_role=current_user.role,
                top_k=top_k,
            )
            blocked_draft = ProcurementAgentVendorDraft(
                vendor_name=draft.vendor_name,
                source_platform=draft.source_platform,
                source_url=draft.source_url,
                contact_name=draft.contact_name,
                contact_email=draft.contact_email,
                contact_phone=draft.contact_phone,
                profile_summary=draft.profile_summary,
                procurement_notes=draft.procurement_notes,
                handles_company_data=draft.handles_company_data,
                requires_system_integration=draft.requires_system_integration,
                quoted_amount=draft.quoted_amount,
                ai_recommendation=recommended_action,
            )
            assessment = self._build_procurement_agent_assessment(
                project,
                blocked_draft,
                review,
                focus_points,
                supplier_profile=supplier_profile,
                material_gate=material_gate,
                requirement_checks=requirement_checks,
                supplier_dossier=supplier_dossier,
            )
            self._upsert_procurement_reviewed_vendor(
                db,
                project=project,
                draft=blocked_draft,
                review=review,
                assessment=assessment,
            )
            return review, assessment, generated_query

        generated_query = self._build_procurement_agent_query(
            project,
            draft,
            focus_points,
            supplier_profile=supplier_profile,
            supplier_dossier=supplier_dossier,
            requirement_checks=requirement_checks,
        )
        review = self.agent_service.query(
            db,
            QueryRequest(
                query=generated_query,
                session_id=None,
                user_role=current_user.role,
                top_k=max(1, min(int(top_k), 10)),
                task_mode="procurement_fit_review",
                tool_sequence=[
                    "retrieve_procurement_knowledge",
                ],
            ),
            current_user=current_user,
        )
        review = self._merge_procurement_tool_trace(
            review,
            material_gate=material_gate,
            requirement_checks=requirement_checks,
            supplier_dossier=supplier_dossier,
        )
        self._ensure_review_trace_id(review)
        reviewed_draft = ProcurementAgentVendorDraft(
            vendor_name=draft.vendor_name,
            source_platform=draft.source_platform,
            source_url=draft.source_url,
            contact_name=draft.contact_name,
            contact_email=draft.contact_email,
            contact_phone=draft.contact_phone,
            profile_summary=draft.profile_summary,
            procurement_notes=draft.procurement_notes,
            handles_company_data=draft.handles_company_data,
            requires_system_integration=draft.requires_system_integration,
            quoted_amount=draft.quoted_amount,
            ai_recommendation=self._derive_procurement_final_recommendation(
                project=project,
                draft=draft,
                review=review,
                material_gate=material_gate,
                requirement_checks=requirement_checks,
                supplier_dossier=supplier_dossier,
                supplier_profile=supplier_profile,
            ),
        )
        assessment = self._build_procurement_agent_assessment(
            project,
            reviewed_draft,
            review,
            focus_points,
            supplier_profile=supplier_profile,
            material_gate=material_gate,
            requirement_checks=requirement_checks,
            supplier_dossier=supplier_dossier,
        )
        review = self._finalize_procurement_tool_trace(
            review,
            assessment=assessment,
        )
        self._upsert_procurement_reviewed_vendor(
            db,
            project=project,
            draft=reviewed_draft,
            review=review,
            assessment=assessment,
        )
        return review, assessment, generated_query

    def _vendor_passed_procurement_baseline(self, vendor: VendorCandidate) -> bool:
        structured_review = self._structured_review_from_json(vendor.ai_review_json)
        if structured_review is None or structured_review.review_kind != "procurement_agent_review":
            return False
        return structured_review.recommendation in {"recommend_proceed", "review_with_risks"}

    def _find_matching_vendor_candidate(
        self,
        db: Session,
        *,
        project_id: str,
        draft: ProcurementAgentVendorDraft,
    ) -> VendorCandidate | None:
        normalized_name = re.sub(r"\s+", " ", draft.vendor_name.strip()).lower()
        normalized_url = draft.source_url.strip().lower()
        for vendor in self.repository.list_vendor_candidates(db, project_id):
            vendor_name = re.sub(r"\s+", " ", (vendor.vendor_name or "").strip()).lower()
            vendor_url = (vendor.source_url or "").strip().lower()
            if normalized_url and vendor_url and normalized_url == vendor_url:
                return vendor
            if normalized_name and vendor_name == normalized_name:
                return vendor
        return None

    def _upsert_procurement_reviewed_vendor(
        self,
        db: Session,
        *,
        project: ProcurementProject,
        draft: ProcurementAgentVendorDraft,
        review,
        assessment: StructuredReviewRead,
    ) -> VendorCandidate | None:
        existing = self._find_matching_vendor_candidate(db, project_id=project.id, draft=draft)
        eligible = assessment.recommendation in {"recommend_proceed", "review_with_risks"}
        if existing is None and not eligible:
            return None
        vendor = existing or self.repository.create_vendor_candidate(
            db,
            project_id=project.id,
            vendor_name=draft.vendor_name,
            source_platform=draft.source_platform,
            source_url=draft.source_url,
            contact_name=draft.contact_name,
            contact_email=draft.contact_email,
            contact_phone=draft.contact_phone,
            profile_summary=draft.profile_summary,
            procurement_notes=draft.procurement_notes,
            handles_company_data=draft.handles_company_data,
            requires_system_integration=draft.requires_system_integration,
            quoted_amount=draft.quoted_amount,
        )
        vendor.vendor_name = draft.vendor_name
        vendor.source_platform = draft.source_platform
        vendor.source_url = draft.source_url
        vendor.contact_name = draft.contact_name
        vendor.contact_email = draft.contact_email
        vendor.contact_phone = draft.contact_phone
        vendor.profile_summary = draft.profile_summary
        vendor.procurement_notes = draft.procurement_notes
        vendor.handles_company_data = draft.handles_company_data
        vendor.requires_system_integration = draft.requires_system_integration
        vendor.quoted_amount = draft.quoted_amount
        vendor.ai_review_summary = review.answer
        vendor.ai_recommendation = assessment.recommendation
        vendor.ai_review_trace_id = review.trace_id
        vendor.ai_review_json = json.dumps(assessment.model_dump(), ensure_ascii=False)
        if existing is not None and not eligible and vendor.status == VendorCandidateStatus.selected.value:
            return vendor
        if eligible and vendor.status in {
            VendorCandidateStatus.rejected.value,
            VendorCandidateStatus.legal_rejected.value,
        }:
            vendor.status = VendorCandidateStatus.candidate.value
        return vendor

    def select_vendor(self, db: Session, project_id: str, vendor_id: str, payload: VendorSelectRequest) -> ProjectDetailRead:
        project = self._require_project(db, project_id)
        self._require_stage(project, ProcurementStage.procurement_sourcing.value)
        vendor = self._require_vendor(db, project.id, vendor_id)
        for item in self.repository.list_vendor_candidates(db, project.id):
            if item.id == vendor.id:
                item.status = VendorCandidateStatus.selected.value
                item.manual_decision = "selected"
                item.manual_reason = payload.reason
            elif item.status == VendorCandidateStatus.selected.value:
                item.status = VendorCandidateStatus.shortlisted.value
        project.selected_vendor_id = vendor.id
        project.vendor_name = vendor.vendor_name
        self._record_manual_decision(
            db,
            project=project,
            subject_type="vendor",
            subject_id=vendor.id,
            decision_type="vendor_selection",
            decision_by=payload.actor_role,
            manual_decision="selected",
            summary=f"已选择目标供应商：{vendor.vendor_name}。",
            reason=payload.reason,
        )
        self._sync_procurement_selection_state(db, project, vendor)
        self._ensure_stage_ready_to_leave(db, project, ProcurementStage.procurement_sourcing.value)
        self._move_project_to_stage(
            db,
            project=project,
            target_stage=ProcurementStage.legal_review.value,
            action="vendor_select",
            actor_role=payload.actor_role,
            reason=payload.reason,
        )
        db.commit()
        return self.get_project_detail(db, project.id)

    def create_artifact(self, db: Session, project_id: str, payload: ProjectArtifactCreate) -> ProjectArtifactRead:
        project = self._require_project(db, project_id)
        artifact = self.repository.create_artifact(
            db,
            project_id=project.id,
            stage=payload.stage,
            artifact_type=payload.artifact_type,
            title=payload.title,
            required=payload.required,
            document_id=payload.document_id,
            linked_vendor_id=payload.linked_vendor_id,
            direction=payload.direction,
            version_no=payload.version_no,
            status=payload.status,
            notes=payload.notes,
        )
        self._refresh_active_stage_blocking_reason(db, project)
        db.commit()
        return ProjectArtifactRead.model_validate(artifact)

    def update_artifact(self, db: Session, project_id: str, artifact_id: str, payload: ProjectArtifactUpdate) -> ProjectArtifactRead:
        project = self._require_project(db, project_id)
        artifact = self.repository.get_artifact(db, artifact_id)
        if artifact is None or artifact.project_id != project_id:
            raise ValueError("Project artifact not found.")
        artifact.status = payload.status
        if payload.notes is not None:
            artifact.notes = payload.notes
        if payload.direction is not None:
            artifact.direction = payload.direction
        if payload.version_no is not None:
            artifact.version_no = payload.version_no
        if payload.document_id:
            artifact.document_id = payload.document_id
        if payload.linked_vendor_id:
            artifact.linked_vendor_id = payload.linked_vendor_id
        self._refresh_active_stage_blocking_reason(db, project)
        db.commit()
        db.refresh(artifact)
        return ProjectArtifactRead.model_validate(artifact)

    def get_artifact_preview(self, db: Session, project_id: str, artifact_id: str) -> ProjectArtifactPreviewRead:
        project = self._require_project(db, project_id)
        artifact = self.repository.get_artifact(db, artifact_id)
        if artifact is None or artifact.project_id != project.id:
            raise ValueError("Project artifact not found.")
        if not artifact.document_id:
            raise ValueError("This artifact has not uploaded a contract file yet.")

        document = db.get(Document, artifact.document_id)
        if document is None:
            raise ValueError("Artifact document not found.")

        text_content = self._build_artifact_preview_text(db, document)
        return ProjectArtifactPreviewRead(
            artifact_id=artifact.id,
            document_id=artifact.document_id,
            title=artifact.title,
            source_title=document.title,
            text_content=text_content,
            content_excerpt=text_content[:400],
        )

    def legal_review(self, db: Session, project_id: str, payload: ProjectLegalReviewRequest) -> ProjectLegalReviewResult:
        project = self._require_project(db, project_id)
        self._require_stage(project, ProcurementStage.legal_review.value)
        selected_vendor = self._require_selected_vendor(db, project)
        self._ensure_legal_review_materials_ready(db, project, selected_vendor)
        contract_comparison = self._build_uploaded_legal_contract_comparison(db, project=project, vendor=selected_vendor)
        query = payload.query.strip() or self._build_default_legal_review_query(
            db,
            project,
            selected_vendor,
            contract_comparison=contract_comparison,
        )
        review = self.agent_service.query(
            db,
            QueryRequest(
                query=query,
                session_id=project.chat_session_id or None,
                user_role=payload.user_role,
                top_k=payload.top_k,
                task_mode="legal_contract_review",
                tool_sequence=[
                    "retrieve_legal_redlines",
                    "compare_legal_clauses",
                ],
            ),
            current_user=UserProfileRead(
                id=f"project-{payload.user_role}",
                username=f"project-{payload.user_role}",
                display_name=f"Project {payload.user_role}",
                role=payload.user_role,
                department=project.department,
                status="active",
            ),
        )
        self._ensure_review_trace_id(review)
        project.chat_session_id = review.session_id
        review = self._attach_legal_contract_comparison(
            db,
            project=project,
            vendor=selected_vendor,
            review=review,
            contract_comparison=contract_comparison,
        )
        structured_review = self._build_legal_structured_review(project, selected_vendor, review)
        review = self._merge_legal_tool_trace(
            db,
            review=review,
            project=project,
            vendor=selected_vendor,
            structured_review=structured_review,
        )
        self._mark_legal_review_completed(db, project, structured_review)
        self.repository.create_decision(
            db,
            project_id=project.id,
            stage=project.current_stage,
            subject_type="vendor",
            subject_id=selected_vendor.id,
            decision_type="legal_ai_review",
            decision_by="system",
            ai_recommendation=self._derive_ai_recommendation(review.next_action, review.debug_summary),
            manual_decision="",
            decision_summary=review.answer,
            structured_summary_json=json.dumps(structured_review.model_dump(), ensure_ascii=False),
            reason="",
            trace_id=review.trace_id,
        )
        self.repository.clear_stage_risks(db, project.id, project.current_stage, linked_vendor_id=selected_vendor.id)
        risks = self._materialize_risks(db, project, review, linked_vendor_id=selected_vendor.id)
        project.risk_level = structured_review.risk_level or self._derive_risk_level(risks, review.next_action)
        self._refresh_active_stage_blocking_reason(db, project)
        db.commit()
        return ProjectLegalReviewResult(
            project=self.get_project_detail(db, project.id),
            review=review,
            assessment=structured_review,
            risks=[ProjectRiskRead.model_validate(risk) for risk in risks],
        )

    def _build_artifact_preview_text(self, db: Session, document: Document) -> str:
        source_path = (document.source_path or "").strip()
        if source_path:
            path = Path(source_path)
            if path.exists() and path.is_file():
                try:
                    source_name = path.name or document.title or "artifact.txt"
                    _, sections = self.document_parser.parse_bytes(name=source_name, data=path.read_bytes())
                    text = "\n\n".join(section.content.strip() for section in sections if section.content.strip())
                    if text:
                        return text[:12000]
                except Exception:
                    pass

        chunks = list(
            db.scalars(
                select(Chunk)
                .where(Chunk.document_id == document.id)
                .order_by(Chunk.order_index.asc())
                .limit(30)
            )
        )
        return "\n\n".join(chunk.content.strip() for chunk in chunks if chunk.content.strip())[:12000]

    def legal_decision(self, db: Session, project_id: str, payload: ProjectLegalDecisionRequest) -> ProjectDetailRead:
        project = self._require_project(db, project_id)
        self._require_stage(project, ProcurementStage.legal_review.value)
        selected_vendor = self._require_selected_vendor(db, project)
        if payload.decision == "approve":
            self._ensure_stage_ready_to_leave(db, project, ProcurementStage.legal_review.value)
            selected_vendor.manual_decision = "approved"
            selected_vendor.manual_reason = payload.reason
            self._record_manual_decision(
                db,
                project=project,
                subject_type="vendor",
                subject_id=selected_vendor.id,
                decision_type="legal_review",
                decision_by=payload.actor_role,
                manual_decision="approved",
                summary="法务审查通过，提交签署。",
                reason=payload.reason,
            )
            self._move_project_to_stage(
                db,
                project=project,
                target_stage=ProcurementStage.signing.value,
                action="legal_approve",
                actor_role=payload.actor_role,
                reason=payload.reason,
            )
        else:
            if not payload.reason.strip():
                raise ValueError("Legal rejection reason is required.")
            selected_vendor.status = VendorCandidateStatus.legal_rejected.value
            selected_vendor.manual_decision = "legal_rejected"
            selected_vendor.manual_reason = payload.reason
            project.selected_vendor_id = ""
            project.vendor_name = ""
            self._record_manual_decision(
                db,
                project=project,
                subject_type="vendor",
                subject_id=selected_vendor.id,
                decision_type="legal_review",
                decision_by=payload.actor_role,
                manual_decision="returned_to_procurement",
                summary="法务审查未通过，退回采购重新筛选供应商。",
                reason=payload.reason,
            )
            self._move_project_to_stage(
                db,
                project=project,
                target_stage=ProcurementStage.procurement_sourcing.value,
                action="legal_return",
                actor_role=payload.actor_role,
                reason=payload.reason,
            )
        db.commit()
        return self.get_project_detail(db, project.id)

    def final_approve(self, db: Session, project_id: str, payload: ProjectFinalApproveRequest) -> ProjectDetailRead:
        project = self._require_project(db, project_id)
        self._require_stage(project, ProcurementStage.final_approval.value)
        self._normalize_optional_approval_stage_requirements(db, project, ProcurementStage.final_approval.value)
        self._ensure_stage_ready_to_leave(db, project, ProcurementStage.final_approval.value)
        self._record_manual_decision(
            db,
            project=project,
            subject_type="project",
            subject_id=project.id,
            decision_type="final_approval",
            decision_by=payload.actor_role,
            manual_decision="approved",
            summary="终审已通过，进入签署归档。",
            reason=payload.reason,
        )
        self._move_project_to_stage(
            db,
            project=project,
            target_stage=ProcurementStage.signing.value,
            action="final_approve",
            actor_role=payload.actor_role,
            reason=payload.reason,
        )
        db.commit()
        return self.get_project_detail(db, project.id)

    def final_return(self, db: Session, project_id: str, payload: ProjectFinalReturnRequest) -> ProjectDetailRead:
        project = self._require_project(db, project_id)
        self._require_stage(project, ProcurementStage.final_approval.value)
        selected_vendor = self._require_selected_vendor(db, project)
        self._record_manual_decision(
            db,
            project=project,
            subject_type="project",
            subject_id=project.id,
            decision_type="final_return",
            decision_by=payload.actor_role,
            manual_decision=f"returned_to_{payload.target_stage}",
            summary=f"终审退回到 {payload.target_stage}。",
            reason=payload.reason,
        )
        if payload.target_stage == ProcurementStage.procurement_sourcing.value:
            selected_vendor.status = VendorCandidateStatus.shortlisted.value
            selected_vendor.manual_decision = "returned_by_final_approval"
            selected_vendor.manual_reason = payload.reason
            project.selected_vendor_id = ""
            project.vendor_name = ""
        self._move_project_to_stage(
            db,
            project=project,
            target_stage=payload.target_stage,
            action="final_return",
            actor_role=payload.actor_role,
            reason=payload.reason,
        )
        db.commit()
        return self.get_project_detail(db, project.id)

    def cancel_project(self, db: Session, project_id: str, payload: ProjectCancelRequest) -> ProjectDetailRead:
        project = self._require_project(db, project_id)
        if project.status != "active" or project.current_stage == ProcurementStage.completed.value:
            raise ValueError("Only active unfinished projects can be cancelled.")
        active_record = self.repository.get_active_stage_record(db, project.id)
        if active_record is not None:
            active_record.status = "completed"
            active_record.ended_at = datetime.utcnow()
            active_record.blocking_reason = payload.reason
        project.status = "cancelled"
        self.repository.create_stage_record(
            db,
            project_id=project.id,
            stage=project.current_stage,
            from_stage=project.current_stage,
            to_stage=project.current_stage,
            action="cancel",
            actor_role=payload.actor_role,
            reason=payload.reason,
            status="completed",
            owner_role=project.current_owner_role,
        ).ended_at = datetime.utcnow()
        self._record_manual_decision(
            db,
            project=project,
            subject_type="project",
            subject_id=project.id,
            decision_type="cancel",
            decision_by=payload.actor_role,
            manual_decision="cancelled",
            summary="项目已取消。",
            reason=payload.reason,
        )
        db.commit()
        return self.get_project_detail(db, project.id)

    def sign_project(self, db: Session, project_id: str, payload: ProjectSignRequest) -> ProjectDetailRead:
        project = self._require_project(db, project_id)
        if project.current_stage == ProcurementStage.final_approval.value:
            self._ensure_stage_defaults(db, project, ProcurementStage.signing.value)
            self._move_project_to_stage(
                db,
                project=project,
                target_stage=ProcurementStage.signing.value,
                action="legacy_final_approval_to_signing",
                actor_role=payload.actor_role,
                reason=payload.reason or "历史最终审批项目转入签署阶段。",
            )
        self._require_stage(project, ProcurementStage.signing.value)
        self._ensure_stage_ready_to_leave(db, project, ProcurementStage.signing.value)
        self._record_manual_decision(
            db,
            project=project,
            subject_type="project",
            subject_id=project.id,
            decision_type="signing",
            decision_by=payload.actor_role,
            manual_decision="signed",
            summary="项目已完成签署并归档。",
            reason=payload.reason,
        )
        self._move_project_to_stage(
            db,
            project=project,
            target_stage=ProcurementStage.completed.value,
            action="sign_complete",
            actor_role=payload.actor_role,
            reason=payload.reason,
        )
        snapshot = self.get_project_detail(db, project.id)
        self.repository.create_archive_snapshot(
            db,
            project_id=project.id,
            stage=ProcurementStage.completed.value,
            snapshot_json=json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False),
        )
        db.commit()
        return self.get_project_detail(db, project.id)

    def get_timeline(self, db: Session, project_id: str) -> list[ProjectTimelineEvent]:
        project = self._require_project(db, project_id)
        events: list[ProjectTimelineEvent] = []
        for stage in self.repository.list_stage_records(db, project.id):
            events.append(
                ProjectTimelineEvent(
                    kind="stage",
                    stage=stage.stage,
                    title=f"{stage.action}: {stage.to_stage or stage.stage}",
                    summary=stage.reason or stage.blocking_reason or f"Owner: {stage.owner_role}",
                    created_at=stage.started_at,
                )
            )
        for decision in self.repository.list_decisions(db, project.id):
            events.append(
                ProjectTimelineEvent(
                    kind="decision",
                    stage=decision.stage,
                    title=decision.decision_type,
                    summary=(decision.decision_summary or decision.reason)[:220],
                    created_at=decision.created_at,
                    trace_id=decision.trace_id,
                )
            )
        for risk in self.repository.list_risks(db, project.id):
            events.append(
                ProjectTimelineEvent(
                    kind="risk",
                    stage=risk.stage,
                    title=f"{risk.severity.title()} risk: {risk.risk_type}",
                    summary=risk.summary,
                    created_at=risk.created_at,
                    trace_id=risk.trace_id,
                )
            )
        for archive in self.repository.list_archive_snapshots(db, project.id):
            events.append(
                ProjectTimelineEvent(
                    kind="archive",
                    stage=archive.stage,
                    title="archive_snapshot",
                    summary="项目已生成归档快照。",
                    created_at=archive.created_at,
                )
            )
        events.sort(key=lambda item: item.created_at)
        return events

    def list_risks(self, db: Session, project_id: str) -> list[ProjectRiskRead]:
        self._require_project(db, project_id)
        return [ProjectRiskRead.model_validate(risk) for risk in self.repository.list_risks(db, project_id)]

    def _require_project(self, db: Session, project_id: str) -> ProcurementProject:
        project = self.repository.get_project(db, project_id)
        if project is None:
            raise ValueError("Procurement project not found.")
        return project

    def _require_vendor(self, db: Session, project_id: str, vendor_id: str) -> VendorCandidate:
        vendor = self.repository.get_vendor_candidate(db, vendor_id)
        if vendor is None or vendor.project_id != project_id:
            raise ValueError("Vendor candidate not found.")
        return vendor

    def _require_selected_vendor(self, db: Session, project: ProcurementProject) -> VendorCandidate:
        if not project.selected_vendor_id:
            raise ValueError("No selected vendor for this project.")
        return self._require_vendor(db, project.id, project.selected_vendor_id)

    def assert_can_create_project(self, current_user: UserProfileRead) -> None:
        if current_user.role not in {"business", "admin"}:
            raise PermissionError("Only business or admin accounts can create projects.")

    def assert_can_create_demo_project(self, current_user: UserProfileRead) -> None:
        if current_user.role != "admin":
            raise PermissionError("Only admin accounts can create demo projects.")

    def assert_can_view_project(self, db: Session, project_id: str, current_user: UserProfileRead) -> None:
        project = self._require_project(db, project_id)
        if not self._can_view_project(db, current_user, project):
            raise PermissionError("Project is not visible to the current account.")

    def assert_can_manage_stage(self, db: Session, project_id: str, current_user: UserProfileRead, action: str) -> None:
        project = self._require_project(db, project_id)
        if not self._can_view_project(db, current_user, project):
            raise PermissionError("Project is not visible to the current account.")
        if action not in self._allowed_actions(project, current_user.role):
            raise PermissionError("Current account cannot perform this action at the current stage.")

    def assert_can_work_on_current_stage(self, db: Session, project_id: str, current_user: UserProfileRead) -> None:
        project = self._require_project(db, project_id)
        if not self._can_view_project(db, current_user, project):
            raise PermissionError("Project is not visible to the current account.")
        allowed_roles = {project.current_owner_role}
        if project.current_stage == ProcurementStage.final_approval.value:
            allowed_roles.add("admin")
        if project.current_stage == ProcurementStage.manager_review.value and current_user.role == "business":
            allowed_roles.add("business")
        if current_user.role not in allowed_roles:
            raise PermissionError("Current account cannot edit tasks or materials in this stage.")

    def _stage_index(self, stage: str) -> int:
        if stage == ProcurementStage.final_approval.value:
            stage = ProcurementStage.signing.value
        try:
            return self.STAGE_ORDER.index(stage)
        except ValueError:
            return -1

    def _can_view_project(self, db: Session, current_user: UserProfileRead, project: ProcurementProject) -> bool:
        role = current_user.role
        if role == "admin":
            return True
        if role == "business":
            return project.created_by_user_id == current_user.id or project.department == current_user.department
        if role == "manager":
            return project.department == current_user.department
        if role == "procurement":
            return self._stage_index(project.current_stage) >= self._stage_index(ProcurementStage.procurement_sourcing.value)
        if role == "legal":
            if self._stage_index(project.current_stage) >= self._stage_index(ProcurementStage.legal_review.value):
                return True
            return any(
                record.stage == ProcurementStage.legal_review.value or record.owner_role == "legal"
                for record in self.repository.list_stage_records(db, project.id)
            )
        return False

    def _sync_business_input_vendor(self, db: Session, project: ProcurementProject) -> None:
        vendors = self.repository.list_vendor_candidates(db, project.id)
        business_input_vendor = next((vendor for vendor in vendors if vendor.source_platform == "business_input"), None)
        if project.vendor_name:
            if business_input_vendor is None:
                self.repository.create_vendor_candidate(
                    db,
                    project_id=project.id,
                    vendor_name=project.vendor_name,
                    source_platform="business_input",
                    source_url="",
                    contact_name="",
                    contact_email="",
                    contact_phone="",
                    profile_summary=project.summary,
                    procurement_notes="业务草稿更新时同步的初始候选供应商。",
                    handles_company_data=bool(project.data_scope and project.data_scope != "none"),
                    requires_system_integration=project.category in {"software", "customer-support-saas"},
                    quoted_amount=float(project.budget_amount or 0),
                )
            elif business_input_vendor.status in {
                VendorCandidateStatus.candidate.value,
                VendorCandidateStatus.shortlisted.value,
            }:
                business_input_vendor.vendor_name = project.vendor_name
                business_input_vendor.profile_summary = project.summary
        elif business_input_vendor is not None and business_input_vendor.status == VendorCandidateStatus.candidate.value:
            business_input_vendor.status = VendorCandidateStatus.rejected.value
            business_input_vendor.manual_decision = "removed_from_draft"
            business_input_vendor.manual_reason = "业务草稿中移除了初始候选供应商。"

    def _require_stage(self, project: ProcurementProject, stage: str) -> None:
        if project.current_stage != stage:
            raise ValueError(f"Project must be in '{stage}' stage.")

    def _move_project_to_stage(
        self,
        db: Session,
        *,
        project: ProcurementProject,
        target_stage: str,
        action: str,
        actor_role: str,
        reason: str,
    ) -> None:
        previous_stage = project.current_stage
        active_record = self.repository.get_active_stage_record(db, project.id)
        if active_record is not None:
            active_record.status = "completed"
            active_record.ended_at = datetime.utcnow()
        blueprint = self.STAGE_BLUEPRINTS.get(target_stage)
        owner_role = blueprint.owner_role if blueprint else "admin"
        project.current_stage = target_stage
        project.current_owner_role = owner_role
        project.status = "completed" if target_stage == ProcurementStage.completed.value else "active"
        record = self.repository.create_stage_record(
            db,
            project_id=project.id,
            stage=target_stage,
            from_stage=previous_stage,
            to_stage=target_stage,
            action=action,
            actor_role=actor_role,
            reason=reason,
            status="completed" if target_stage == ProcurementStage.completed.value else "active",
            owner_role=owner_role,
        )
        if target_stage == ProcurementStage.completed.value:
            record.ended_at = datetime.utcnow()
        self._ensure_stage_defaults(db, project, target_stage)
        if target_stage == ProcurementStage.legal_review.value and project.selected_vendor_id:
            try:
                selected_vendor = self._require_selected_vendor(db, project)
            except ValueError:
                selected_vendor = None
            if selected_vendor is not None:
                self._sync_legal_review_handoff_state(db, project, selected_vendor)
        self._refresh_active_stage_blocking_reason(db, project)

    def _ensure_stage_defaults(self, db: Session, project: ProcurementProject, stage: str) -> None:
        blueprint = self.STAGE_BLUEPRINTS.get(stage)
        if blueprint is None:
            return
        self._normalize_optional_approval_stage_requirements(db, project, stage)
        if stage in {ProcurementStage.manager_review.value, ProcurementStage.final_approval.value}:
            return
        existing_tasks = {(task.stage, task.title) for task in self.repository.list_tasks(db, project.id)}
        existing_artifacts = {
            (artifact.stage, artifact.title, artifact.linked_vendor_id)
            for artifact in self.repository.list_artifacts(db, project.id)
        }
        linked_vendor_id = project.selected_vendor_id if stage == ProcurementStage.legal_review.value else ""
        for task_type, title, assignee_role in blueprint.required_tasks:
            if (stage, title) not in existing_tasks:
                self.repository.create_task(
                    db,
                    project_id=project.id,
                    stage=stage,
                    task_type=task_type,
                    title=title,
                    details="",
                    assignee_role=assignee_role,
                    required=True,
                )
        for artifact_type, title, direction in blueprint.required_artifacts:
            if (stage, title, linked_vendor_id) not in existing_artifacts:
                self.repository.create_artifact(
                    db,
                    project_id=project.id,
                    stage=stage,
                    artifact_type=artifact_type,
                    title=title,
                    required=True,
                    document_id="",
                    linked_vendor_id=linked_vendor_id,
                    direction=direction,
                    version_no=1,
                    status="missing",
                    notes="系统内置流转材料。",
                )

    def _normalize_optional_approval_stage_requirements(self, db: Session, project: ProcurementProject, stage: str) -> None:
        if stage not in {ProcurementStage.manager_review.value, ProcurementStage.final_approval.value}:
            return
        for task in self.repository.list_tasks(db, project.id):
            if task.stage == stage and task.required:
                task.required = False
        for artifact in self.repository.list_artifacts(db, project.id):
            if artifact.stage == stage and artifact.required:
                artifact.required = False

    def _build_application_checks(self, project: ProcurementProject) -> list[RequirementCheckRead]:
        return [
            RequirementCheckRead(
                key="title",
                label="Project title captured",
                checked=bool(project.title.strip()),
                detail="Project title is filled in." if project.title.strip() else "Please fill in the procurement project title.",
            ),
            RequirementCheckRead(
                key="requester",
                label="Requester and department captured",
                checked=bool(project.requester_name.strip()) and bool(project.department.strip()),
                detail="Requester and department are filled in." if project.requester_name.strip() and project.department.strip() else "Please fill in requester and department.",
            ),
            RequirementCheckRead(
                key="purpose",
                label="Procurement purpose described",
                checked=bool(project.summary.strip()),
                detail="Procurement purpose and scenario are filled in." if project.summary.strip() else "Please describe the procurement purpose, scope, and business scenario.",
            ),
            RequirementCheckRead(
                key="budget",
                label="Budget captured",
                checked=project.budget_amount > 0,
                detail="Budget amount is filled in." if project.budget_amount > 0 else "Please provide a budget amount greater than 0.",
            ),
            RequirementCheckRead(
                key="business_value",
                label="Business value described",
                checked=bool(project.business_value.strip()),
                detail="Business value is filled in." if project.business_value.strip() else "Please describe the expected business value or benefit.",
            ),
            RequirementCheckRead(
                key="target_go_live_date",
                label="Go-live target captured",
                checked=bool(project.target_go_live_date.strip()),
                detail="Target go-live date is filled in." if project.target_go_live_date.strip() else "Please provide the expected go-live date.",
            ),
            RequirementCheckRead(
                key="data_scope",
                label="Data scope identified",
                checked=bool(project.data_scope.strip()),
                detail="Data scope is identified." if project.data_scope.strip() else "Please clarify whether the project involves customer or sensitive data.",
            ),
        ]

    def _application_form_ready(self, project: ProcurementProject) -> bool:
        return all(item.checked for item in self._build_application_checks(project))

    def _application_form_summary(self, project: ProcurementProject) -> str:
        checks = self._build_application_checks(project)
        passed_count = sum(1 for item in checks if item.checked)
        total_count = len(checks)
        if passed_count == total_count:
            return f"The procurement application form passed all checks ({passed_count}/{total_count}) and can move to manager review."
        return f"The procurement application form currently satisfies {passed_count}/{total_count} checks. Complete the missing items before submission."

    def _sync_business_draft_form_state(self, db: Session, project: ProcurementProject) -> None:
        if project.current_stage != ProcurementStage.business_draft.value:
            return
        self._ensure_stage_defaults(db, project, ProcurementStage.business_draft.value)
        form_ready = self._application_form_ready(project)
        summary = self._application_form_summary(project)
        for task in self.repository.list_tasks(db, project.id):
            if task.stage != ProcurementStage.business_draft.value or not task.required:
                continue
            task.details = "The system-maintained procurement application form is updated automatically as business fields change."
            task.status = "done" if form_ready else "pending"
        for artifact in self.repository.list_artifacts(db, project.id):
            if artifact.stage != ProcurementStage.business_draft.value or artifact.artifact_type != "procurement_application_form":
                continue
            artifact.direction = "internal"
            artifact.version_no = 1
            artifact.notes = summary
            artifact.status = "provided" if form_ready else "missing"

    def _sync_procurement_selection_state(
        self,
        db: Session,
        project: ProcurementProject,
        vendor: VendorCandidate,
    ) -> None:
        if project.current_stage != ProcurementStage.procurement_sourcing.value:
            return
        self._ensure_stage_defaults(db, project, ProcurementStage.procurement_sourcing.value)
        review = self._structured_review_from_json(vendor.ai_review_json)
        recommendation = review.recommendation if review is not None else vendor.ai_recommendation or "review_with_risks"
        conclusion = review.conclusion if review is not None else vendor.ai_review_summary or "Procurement selected the supplier after the sourcing review."
        for task in self.repository.list_tasks(db, project.id):
            if task.stage != ProcurementStage.procurement_sourcing.value or not task.required:
                continue
            if task.task_type == "sourcing" and "比选" not in task.title:
                task.status = "done"
                task.details = f"Supplier materials were collected and parsed for {vendor.vendor_name}."
            elif task.task_type == "sourcing":
                task.status = "done"
                task.details = f"System review finished. Current recommendation: {recommendation}."
            elif task.task_type == "selection":
                task.status = "done"
                task.details = f"Procurement selected {vendor.vendor_name} as the target supplier."
        for artifact in self.repository.list_artifacts(db, project.id):
            if artifact.stage != ProcurementStage.procurement_sourcing.value or not artifact.required:
                continue
            artifact.direction = "internal"
            artifact.version_no = max(int(artifact.version_no or 1), 1)
            if artifact.artifact_type == "vendor_comparison_sheet":
                artifact.status = "provided"
                artifact.notes = f"System comparison completed. Current target supplier: {vendor.vendor_name}."
            elif artifact.artifact_type == "procurement_recommendation":
                artifact.status = "provided"
                artifact.linked_vendor_id = vendor.id
                artifact.notes = conclusion

    def _vendor_contact_summary(self, vendor: VendorCandidate) -> str:
        contact_bits = [
            f"Contact: {vendor.contact_name}" if (vendor.contact_name or "").strip() else "",
            f"Email: {vendor.contact_email}" if (vendor.contact_email or "").strip() else "",
            f"Phone: {vendor.contact_phone}" if (vendor.contact_phone or "").strip() else "",
            f"Public source: {vendor.source_url}" if (vendor.source_url or "").strip() else "",
        ]
        summary = "; ".join(item for item in contact_bits if item)
        return summary or "No direct contact details were captured yet. Legal can use the public source as the initial contact path."

    def _sync_legal_review_handoff_state(
        self,
        db: Session,
        project: ProcurementProject,
        vendor: VendorCandidate,
    ) -> None:
        if project.current_stage != ProcurementStage.legal_review.value:
            return
        contract_summary = self._vendor_contact_summary(vendor)
        for task in self.repository.list_tasks(db, project.id):
            if task.stage != ProcurementStage.legal_review.value or not task.required:
                continue
            task.details = (
                "请先确认已上传我方采购合同与对方修改后的采购合同，再运行法务红线审查。"
                f" 当前供应商信息：{contract_summary}"
            )
        for artifact in self.repository.list_artifacts(db, project.id):
            if artifact.stage != ProcurementStage.legal_review.value:
                continue
            if artifact.artifact_type in self.LEGAL_OUR_CONTRACT_ARTIFACT_TYPES:
                artifact.linked_vendor_id = vendor.id
                artifact.direction = "internal"
                artifact.notes = "请上传本公司采购合同版本，作为法务红线对比的基准文本。"
            elif artifact.artifact_type in self.LEGAL_COUNTERPARTY_CONTRACT_ARTIFACT_TYPES:
                artifact.linked_vendor_id = vendor.id
                artifact.direction = "inbound"
                artifact.notes = "请上传对方修改后的采购合同版本，系统将与我方合同做逐条对比。"

    def _build_default_legal_review_query(
        self,
        db: Session,
        project: ProcurementProject,
        vendor: VendorCandidate,
        *,
        contract_comparison: dict[str, object] | None = None,
    ) -> str:
        vendor_name = vendor.vendor_name.strip() or "当前供应商"
        artifacts = self.repository.list_artifacts(db, project.id)
        our_artifact = self._artifact_for_vendor(
            artifacts,
            ProcurementStage.legal_review.value,
            self.LEGAL_OUR_CONTRACT_ARTIFACT_TYPES,
            vendor.id,
        )
        counterparty_artifact = self._artifact_for_vendor(
            artifacts,
            ProcurementStage.legal_review.value,
            self.LEGAL_COUNTERPARTY_CONTRACT_ARTIFACT_TYPES,
            vendor.id,
        )
        our_title = self._legal_artifact_document_title(db, our_artifact, fallback_title="我方采购合同")
        counterparty_title = self._legal_artifact_document_title(db, counterparty_artifact, fallback_title="对方修改后的采购合同")
        compact_differences = self._legal_compact_difference_summary(contract_comparison or {})
        semantic_differences = self._legal_semantic_difference_summary(contract_comparison or {})
        key_snippets = self._legal_compact_evidence_summary(contract_comparison or {})
        retrieval_topics = self._legal_retrieval_topics(contract_comparison or {})
        project_context = self._legal_project_context_summary(project)
        lines = [
            "法务合同红线审查",
            f"项目={project.title}",
            f"供应商={vendor_name}",
            f"我方合同={our_title}",
            f"对方合同={counterparty_title}",
            f"业务场景={project_context}",
            f"差异摘要={compact_differences or '未识别到明确缺失或弱化条款，按核心红线复核'}",
        ]
        if semantic_differences:
            lines.append(f"差异描述={semantic_differences}")
        if key_snippets:
            lines.append(f"合同片段={key_snippets}")
        lines.extend(
            [
                f"检索主题={retrieval_topics}",
                "审查关注=需要判断这些改动是否突破公司在赔付边界、监督核查、数据控制、服务承诺、付款安排或争议处理上的底线",
                "输出要求=结合合同差异和制度依据，给出风险原因、引用依据、建议动作；仅作为法务辅助审查，不替代最终法律意见",
            ]
        )
        return "\n".join(lines)

    def _legal_project_context_summary(self, project: ProcurementProject) -> str:
        parts: list[str] = []
        if project.summary:
            parts.append(project.summary.strip())
        data_scope_label = self._legal_data_scope_label(project.data_scope)
        if data_scope_label:
            parts.append(data_scope_label)
        budget_label = self._legal_budget_label(project.budget_amount)
        if budget_label:
            parts.append(budget_label)
        if project.category:
            parts.append(f"采购类型为{project.category}")
        if project.business_value:
            parts.append(project.business_value.strip())
        return "；".join(list(dict.fromkeys(part for part in parts if part))[:5])

    @staticmethod
    def _legal_data_scope_label(data_scope: str) -> str:
        normalized = (data_scope or "").strip().lower()
        mapping = {
            "none": "当前项目原则上不涉及正式客户或生产业务数据",
            "customer_data": "项目会涉及客户服务记录、工单内容或相关业务数据",
            "employee_data": "项目会涉及员工或内部运营数据",
            "customer_support_data": "项目会涉及客服会话、工单附件和服务记录",
            "cross_border_customer_data": "项目会涉及跨境流转的客户服务或业务数据",
            "migration_data": "项目包含历史业务数据迁移和过渡期处理安排",
        }
        if not normalized:
            return ""
        return mapping.get(normalized, f"项目数据范围为{data_scope}")

    @staticmethod
    def _legal_budget_label(budget_amount: float | int | None) -> str:
        amount = float(budget_amount or 0)
        if amount <= 0:
            return ""
        if amount <= 50000:
            return "预算规模较小，属于试运行或轻量验证级别"
        if amount <= 300000:
            return "预算规模中等，需要兼顾交付效率与合同风险"
        return "预算规模较大，按正式采购和标准红线审查"

    def _legal_compact_difference_summary(self, comparison_view: dict[str, object]) -> str:
        entries: list[str] = []
        for label, key in (("缺失", "strict_missing_clauses"), ("弱化", "weakened_clauses")):
            clauses_by_doc = comparison_view.get(key, {})
            if not isinstance(clauses_by_doc, dict):
                continue
            for clauses in clauses_by_doc.values():
                if not isinstance(clauses, list):
                    continue
                for clause in clauses[:6]:
                    clause_name = str(clause).strip()
                    if clause_name:
                        entries.append(f"{clause_name}{label}")
        return "；".join(list(dict.fromkeys(entries))[:8])

    def _legal_semantic_difference_summary(self, comparison_view: dict[str, object]) -> str:
        entries: list[str] = []
        for label, key in (("缺失", "strict_missing_clauses"), ("弱化", "weakened_clauses")):
            clauses_by_doc = comparison_view.get(key, {})
            if not isinstance(clauses_by_doc, dict):
                continue
            for clauses in clauses_by_doc.values():
                if not isinstance(clauses, list):
                    continue
                for clause in clauses[:6]:
                    clause_name = str(clause).strip()
                    concern = self.LEGAL_CONCERN_DESCRIPTIONS.get(clause_name, clause_name)
                    if not concern:
                        continue
                    if label == "缺失":
                        entries.append(f"对方版本没有保留“{concern}”相关约束")
                    else:
                        entries.append(f"对方版本在“{concern}”方面做了更宽松的修改")
        return "；".join(list(dict.fromkeys(entries))[:6])

    def _legal_compact_evidence_summary(self, comparison_view: dict[str, object]) -> str:
        snippets: list[str] = []
        clause_evidence = comparison_view.get("clause_evidence", {})
        if not isinstance(clause_evidence, dict):
            return ""
        for clause_name, doc_map in clause_evidence.items():
            if not isinstance(doc_map, dict):
                continue
            for snippet in doc_map.values():
                text = re.sub(r"\s+", " ", str(snippet).strip())
                if not text:
                    continue
                snippets.append(text[:70])
                break
        return " | ".join(list(dict.fromkeys(snippets))[:4])

    def _legal_retrieval_topics(self, comparison_view: dict[str, object]) -> str:
        topics = ["云服务合同底线", "标准模板要求", "供应商回传修改处理"]
        focus_clauses = self._legal_focus_clauses(comparison_view)
        clause_topic_map = {
            "数据处理": "数据与安全边界",
            "安全事件通知": "事故响应与通知时效",
            "保密义务": "保密信息使用边界",
            "争议解决与适用法律": "争议处理与适用法律",
            "付款条款": "付款节奏与商业合理性",
            "服务水平": "服务承诺与违约责任",
            "审计权": "监督核查与证据配合",
            "责任上限": "责任承担范围",
            "赔偿责任": "违约或侵权后的赔付安排",
            "便利终止": "退出机制与提前解约",
        }
        for clause in focus_clauses:
            mapped = clause_topic_map.get(clause)
            if mapped:
                topics.append(mapped)
        return "、".join(list(dict.fromkeys(topics))[:6])

    def _legal_focus_clauses(self, comparison_view: dict[str, object]) -> list[str]:
        clauses: list[str] = []
        for key in ("blocking_clauses", "watch_clauses", "strict_missing_clauses", "weakened_clauses"):
            clauses_by_doc = comparison_view.get(key, {})
            if not isinstance(clauses_by_doc, dict):
                continue
            for values in clauses_by_doc.values():
                if not isinstance(values, list):
                    continue
                clauses.extend(str(item).strip() for item in values if str(item).strip())
        return list(dict.fromkeys(clauses))

    def _legal_artifact_document_title(
        self,
        db: Session,
        artifact: ProjectArtifact | None,
        *,
        fallback_title: str,
    ) -> str:
        if artifact is None or not artifact.document_id:
            return fallback_title
        document = db.get(Document, artifact.document_id)
        return document.title if document else artifact.title or fallback_title

    def _collect_legal_material_blockers(
        self,
        artifacts: list[ProjectArtifact],
        linked_vendor_id: str,
    ) -> list[str]:
        blockers: list[str] = []
        if not self._has_stage_artifact(
            artifacts,
            ProcurementStage.legal_review.value,
            self.LEGAL_OUR_CONTRACT_ARTIFACT_TYPES,
            linked_vendor_id,
        ):
            blockers.append("法务审查缺少我方采购合同。")
        if not self._has_stage_artifact(
            artifacts,
            ProcurementStage.legal_review.value,
            self.LEGAL_COUNTERPARTY_CONTRACT_ARTIFACT_TYPES,
            linked_vendor_id,
        ):
            blockers.append("法务审查缺少对方修改后的采购合同。")
        return blockers

    def _ensure_legal_review_materials_ready(
        self,
        db: Session,
        project: ProcurementProject,
        vendor: VendorCandidate,
    ) -> None:
        artifacts = self.repository.list_artifacts(db, project.id)
        blockers = self._collect_legal_material_blockers(artifacts, vendor.id)
        if blockers:
            raise ValueError("；".join(blockers))

    def _mark_legal_review_completed(
        self,
        db: Session,
        project: ProcurementProject,
        structured_review: StructuredReviewRead,
    ) -> None:
        for task in self.repository.list_tasks(db, project.id):
            if task.stage != ProcurementStage.legal_review.value or not task.required:
                continue
            task.status = "done"
            task.details = (
                f"法务红线审查已完成。建议动作：{structured_review.decision_suggestion or 'manual_review'}；"
                f"风险等级：{structured_review.risk_level}。"
            )

    def _ensure_review_trace_id(self, review) -> None:
        if getattr(review, "trace_id", ""):
            return
        review.trace_id = str(uuid.uuid4())

    def _ensure_stage_ready_to_leave(self, db: Session, project: ProcurementProject, stage: str) -> None:
        blockers = self._collect_blockers(
            project,
            self.repository.list_tasks(db, project.id),
            self.repository.list_artifacts(db, project.id),
            self.repository.list_vendor_candidates(db, project.id),
            stage,
        )
        if blockers:
            raise ValueError("Current stage still has unresolved blockers.")

    def _collect_blockers(
        self,
        project: ProcurementProject,
        tasks: list[ProjectTask],
        artifacts: list[ProjectArtifact],
        vendors: list[VendorCandidate],
        current_stage: str,
    ) -> list[str]:
        if project.status in {"cancelled", "completed"}:
            return []
        blockers: list[str] = []
        if current_stage == ProcurementStage.business_draft.value:
            for item in self._build_application_checks(project):
                if not item.checked:
                    blockers.append(f"采购申表未完成: {item.label}")
            return blockers
        for task in tasks:
            if task.stage == current_stage and task.required and task.status != "done":
                blockers.append(f"Task pending: {task.title}")
        if current_stage != ProcurementStage.legal_review.value:
            for artifact in artifacts:
                if artifact.stage != current_stage or not artifact.required:
                    continue
                if artifact.status not in {"provided", "approved"}:
                    blockers.append(f"Artifact missing: {artifact.title}")
        if current_stage == ProcurementStage.procurement_sourcing.value and not project.selected_vendor_id:
            blockers.append("Target vendor has not been selected.")
        if current_stage == ProcurementStage.legal_review.value:
            if not project.selected_vendor_id:
                blockers.append("No selected vendor is attached to legal review.")
            blockers.extend(self._collect_legal_material_blockers(artifacts, project.selected_vendor_id))
        if current_stage == ProcurementStage.final_approval.value and not project.selected_vendor_id:
            blockers.append("Final approval requires a selected vendor.")
        return blockers

    def _has_stage_artifact(
        self,
        artifacts: list[ProjectArtifact],
        stage: str,
        artifact_type: str | tuple[str, ...],
        linked_vendor_id: str,
    ) -> bool:
        artifact_types = {artifact_type} if isinstance(artifact_type, str) else set(artifact_type)
        for artifact in artifacts:
            if artifact.stage != stage or artifact.artifact_type not in artifact_types:
                continue
            if linked_vendor_id and artifact.linked_vendor_id not in {"", linked_vendor_id}:
                continue
            if artifact.status in {"provided", "approved"}:
                return True
        return False

    def _refresh_active_stage_blocking_reason(self, db: Session, project: ProcurementProject) -> None:
        active_record = self.repository.get_active_stage_record(db, project.id)
        if active_record is None:
            return
        self._normalize_optional_approval_stage_requirements(db, project, project.current_stage)
        self._sync_business_draft_form_state(db, project)
        blockers = self._collect_blockers(
            project,
            self.repository.list_tasks(db, project.id),
            self.repository.list_artifacts(db, project.id),
            self.repository.list_vendor_candidates(db, project.id),
            project.current_stage,
        )
        active_record.blocking_reason = " | ".join(blockers[:5]) if blockers else ""

    def _record_manual_decision(
        self,
        db: Session,
        *,
        project: ProcurementProject,
        subject_type: str,
        subject_id: str,
        decision_type: str,
        decision_by: str,
        manual_decision: str,
        summary: str,
        reason: str,
    ) -> None:
        self.repository.create_decision(
            db,
            project_id=project.id,
            stage=project.current_stage,
            subject_type=subject_type,
            subject_id=subject_id,
            decision_type=decision_type,
            decision_by=decision_by,
            ai_recommendation="",
            manual_decision=manual_decision,
            decision_summary=summary,
            structured_summary_json="{}",
            reason=reason,
            trace_id="",
        )

    def _materialize_risks(self, db: Session, project: ProcurementProject, review, *, linked_vendor_id: str) -> list[ProjectRisk]:
        debug_summary = review.debug_summary or {}
        risk_flags = list(debug_summary.get("risk_flags", []))
        comparison_view = debug_summary.get("comparison_view")
        if isinstance(comparison_view, dict):
            risk_flags.extend(comparison_view.get("risk_flags", []))
        if not risk_flags and review.next_action != "answer":
            risk_flags.append("manual_follow_up_required")
        risks: list[ProjectRisk] = []
        for flag in dict.fromkeys(risk_flags):
            risks.append(
                self.repository.create_risk(
                    db,
                    project_id=project.id,
                    linked_vendor_id=linked_vendor_id,
                    stage=project.current_stage,
                    risk_type=str(flag),
                    severity=self._risk_severity_from_flag(str(flag)),
                    summary=self._risk_summary_from_flag(str(flag)),
                    status="open",
                    trace_id=review.trace_id,
                )
            )
        return risks

    def _derive_ai_recommendation(self, next_action: str, debug_summary: dict[str, object]) -> str:
        risk_flags = list(debug_summary.get("risk_flags", []))
        comparison_view = debug_summary.get("comparison_view")
        if isinstance(comparison_view, dict):
            risk_flags.extend(comparison_view.get("risk_flags", []))
        if next_action != "answer":
            return "needs_follow_up"
        if risk_flags:
            return "review_with_risks"
        return "recommend_proceed"

    def _risk_summary_from_flag(self, flag: str) -> str:
        mapping = {
            "missing_audit_rights": "Supplier response appears to weaken or remove audit rights.",
            "missing_security_incident_notice": "Security incident notification terms appear insufficient or missing.",
            "missing_data_processing_terms": "Data processing protections require legal or privacy review.",
            "liability_cap_weakened": "Liability cap language appears weaker than the standard template.",
            "unknown_data_residency": "Data hosting or residency location is not clear for a data-related supplier.",
            "unclear_subprocessor_arrangements": "Subprocessor or outsourcing arrangements are mentioned but not clearly explained.",
            "manual_follow_up_required": "Evidence is not strong enough for automatic progression and needs manual review.",
        }
        if re.search(r"[\u4e00-\u9fff]", flag):
            return flag
        return mapping.get(flag, f"Review flagged risk: {flag.replace('_', ' ')}.")

    def _risk_severity_from_flag(self, flag: str) -> str:
        if re.search(r"(缺少|弱化|红线|责任上限|数据处理|审计权)", flag):
            return "high"
        if flag in {"missing_audit_rights", "missing_data_processing_terms", "liability_cap_weakened", "unknown_data_residency"}:
            return "high"
        if flag in {"missing_security_incident_notice", "manual_follow_up_required", "unclear_subprocessor_arrangements"}:
            return "medium"
        return "low"

    def _derive_risk_level(self, risks: list[ProjectRisk], next_action: str) -> str:
        severities = {risk.severity for risk in risks}
        if "high" in severities:
            return "high"
        if next_action != "answer" or "medium" in severities:
            return "medium"
        return "low"

    def _extract_vendor_draft_from_materials(
        self,
        project: ProcurementProject,
        materials: list[ProcurementMaterialText],
        current_user: UserProfileRead,
    ) -> tuple[ProcurementAgentVendorDraft, str, list[str], SupplierProfileInsights]:
        combined_text = "\n\n".join(item.text for item in materials)
        urls = list(self._find_valid_source_urls(combined_text))
        supplier_profile = self._extract_supplier_profile_with_llm(project, materials, combined_text)
        vendor_name = self._extract_vendor_name(combined_text, materials) or supplier_profile.vendor_name
        source_url = (urls[0] if urls else "") or (supplier_profile.source_urls[0] if supplier_profile.source_urls else "")
        source_platform = self._extract_source_platform(source_url, materials)
        contact_name = self._extract_contact_name(combined_text)
        contact_email = self._extract_contact_email(combined_text)
        contact_phone = self._extract_contact_phone(combined_text)
        profile_summary = self._merge_profile_summary(self._extract_profile_summary(combined_text), supplier_profile)
        procurement_notes = self._build_procurement_notes(
            project,
            materials,
            combined_text,
            current_user,
            supplier_profile=supplier_profile,
        )
        warnings: list[str] = []

        if not vendor_name:
            warnings.append("未能稳定识别供应商名称，建议人工补充。")
            vendor_name = materials[0].name.rsplit(".", 1)[0][:60]
        if not source_url:
            warnings.append("材料中未识别出明确来源链接，建议补充官网或第三方平台链接。")
        if len(profile_summary) < 20:
            warnings.append("提取到的供应商简介较少，建议补充公司介绍、官网简介或白皮书。")

        if supplier_profile.extraction_mode == "rules_only":
            warnings.append("Current extraction used rule-only mode because no LLM enhancement was available.")

        summary = (
            f"Parsed {len(materials)} supplier material(s) and generated a draft profile. "
            f"Identified supplier: {vendor_name or 'manual confirmation required'}. "
            "The procurement draft fields were populated automatically."
        )
        return (
            ProcurementAgentVendorDraft(
                vendor_name=vendor_name,
                source_platform=source_platform,
                source_url=source_url,
                contact_name=contact_name,
                contact_email=contact_email,
                contact_phone=contact_phone,
                profile_summary=profile_summary,
                procurement_notes=procurement_notes,
            ),
            summary,
            list(dict.fromkeys(warnings)),
            supplier_profile,
        )

    def _extract_vendor_name(self, combined_text: str, materials: list[ProcurementMaterialText]) -> str:
        direct_match = re.search(
            r"(?:Vendor Name|Company Name|供应商名称|公司名称|企业名称)\s*[:：]\s*([^\n\r;]{2,80})",
            combined_text,
            flags=re.IGNORECASE,
        )
        if direct_match:
            return direct_match.group(1).strip(" ：:;；。")

        patterns = [
            r"(?:Vendor Name|Company Name|Vendor|Supplier)\s*:\s*([^\n\r;]{2,80})",
            r"(?:Vendor|Supplier)\s*:\s*([^\n\r;]{2,80})",
        ]
        for pattern in patterns:
            match = re.search(pattern, combined_text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip(" :;")

        first_meaningful_line = ""
        for item in materials:
            for line in item.text.splitlines():
                cleaned = line.strip(" #*-")
                if 3 <= len(cleaned) <= 80:
                    first_meaningful_line = cleaned
                    break
            if first_meaningful_line:
                break
        trailing_ascii_name = ""
        if first_meaningful_line:
            ascii_name_match = re.search(r"([A-Z][A-Za-z0-9 .,&-]{2,80})$", first_meaningful_line)
            if ascii_name_match:
                trailing_ascii_name = ascii_name_match.group(1).strip(" :;,.")
        if trailing_ascii_name:
            return trailing_ascii_name
        if first_meaningful_line and not re.search(r"(whitepaper|policy|contract|terms)", first_meaningful_line, flags=re.IGNORECASE):
            return first_meaningful_line
        return ""

    def _extract_source_platform(self, source_url: str, materials: list[ProcurementMaterialText]) -> str:
        if source_url:
            host = urlparse(source_url).netloc.lower().replace("www.", "")
            if host:
                return host
        source_types = {item.source_type for item in materials}
        if "pdf" in source_types or "docx" in source_types:
            return "uploaded_material"
        return materials[0].source_type or "uploaded_material"

    def _extract_contact_name(self, combined_text: str) -> str:
        patterns = [
            r"(?:Contact|Contact Person|Business Contact|Procurement Contact)\s*:\s*([^\n\r:;]{2,40})",
        ]
        for pattern in patterns:
            match = re.search(pattern, combined_text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip(" :;")
        return ""

    def _extract_contact_email(self, combined_text: str) -> str:
        match = re.search(r"([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", combined_text, flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _extract_contact_phone(self, combined_text: str) -> str:
        patterns = [
            r"(?:Phone|Tel|Mobile)\s*:?\s*([+\d][\d\s\-()]{6,20})",
            r"(\+?\d[\d\s\-()]{8,20}\d)",
        ]
        for pattern in patterns:
            match = re.search(pattern, combined_text, flags=re.IGNORECASE)
            if not match:
                continue
            phone = re.sub(r"\s+", " ", match.group(1)).strip()
            if len(re.sub(r"\D", "", phone)) >= 7:
                return phone
        return ""

    def _extract_profile_summary(self, combined_text: str) -> str:
        segments = re.split(r"[\n。；;!?！？]+", combined_text)
        picked: list[str] = []
        for segment in segments:
            cleaned = re.sub(r"\s+", " ", segment).strip(" -:#")
            if len(cleaned) < 12:
                continue
            if any(token in cleaned.lower() for token in ["报价", "price", "invoice", "发票"]):
                continue
            if cleaned in picked:
                continue
            picked.append(cleaned)
            if len(picked) >= 3:
                break
        return "；".join(picked)[:400]

    def _build_procurement_notes(
        self,
        project: ProcurementProject,
        materials: list[ProcurementMaterialText],
        combined_text: str,
        current_user: UserProfileRead,
        supplier_profile: SupplierProfileInsights | None = None,
    ) -> str:
        note_lines = [
            f"{current_user.display_name or 'Procurement'} uploaded {len(materials)} supplier material(s). Review the extracted draft before continuing.",
            f"Current project: {project.title}. Category: {project.category or 'unspecified'}.",
            f"Materials: {', '.join(item.name for item in materials[:4])}",
        ]
        lowered = combined_text.lower()
        if "price" in lowered or "fee" in lowered or "报价" in combined_text:
            note_lines.append("Commercial or pricing terms were detected in the materials.")
        if project.data_scope != "none" or "data" in lowered or "数据" in combined_text:
            note_lines.append("The project or materials suggest a data-processing scenario, so compliance and security should be checked closely.")
        if "agreement" in lowered or "msa" in lowered or "合同" in combined_text:
            note_lines.append("Contract-related content was detected and can be reused in the legal review stage.")
        if supplier_profile:
            if supplier_profile.data_involvement:
                note_lines.append(f"LLM-detected data signal: {supplier_profile.data_involvement}")
            if supplier_profile.security_signals:
                note_lines.append(f"LLM-detected security signals: {'; '.join(supplier_profile.security_signals[:3])}")
            if supplier_profile.legal_signals:
                note_lines.append(f"LLM-detected legal signals: {'; '.join(supplier_profile.legal_signals[:3])}")
            if supplier_profile.missing_materials:
                note_lines.append(f"LLM-detected missing materials: {'; '.join(supplier_profile.missing_materials[:3])}")
        return " ".join(note_lines)[:500]
    def _extract_supplier_profile_with_llm(
        self,
        project: ProcurementProject,
        materials: list[ProcurementMaterialText],
        combined_text: str,
    ) -> SupplierProfileInsights:
        llm_client = getattr(self.agent_service, "llm_client", None)
        if llm_client is None or not hasattr(llm_client, "extract_supplier_profile"):
            return SupplierProfileInsights()
        payload = llm_client.extract_supplier_profile(
            project_context={
                "title": project.title,
                "category": project.category,
                "data_scope": project.data_scope,
                "department": project.department,
            },
            combined_text=combined_text,
            material_names=[item.name for item in materials],
        )
        if not isinstance(payload, dict):
            return SupplierProfileInsights()

        def _as_text(key: str, limit: int = 400) -> str:
            return str(payload.get(key, "")).strip()[:limit]

        def _as_list(key: str, limit: int = 6) -> tuple[str, ...]:
            raw_value = payload.get(key, [])
            if isinstance(raw_value, str):
                raw_items = [item.strip() for item in re.split(r"[\n;,，；]+", raw_value) if item.strip()]
            elif isinstance(raw_value, list):
                raw_items = [str(item).strip() for item in raw_value if str(item).strip()]
            else:
                raw_items = []
            return tuple(dict.fromkeys(raw_items))[:limit]

        confidence_raw = payload.get("confidence", 0.0)
        try:
            confidence = max(0.0, min(float(confidence_raw), 1.0))
        except (TypeError, ValueError):
            confidence = 0.0

        return SupplierProfileInsights(
            extraction_mode="hybrid_llm",
            confidence=confidence,
            vendor_name=_as_text("vendor_name", limit=120),
            company_summary=_as_text("company_summary", limit=500),
            products_services=_as_text("products_services", limit=300),
            data_involvement=_as_text("data_involvement", limit=240),
            security_signals=_as_list("security_signals"),
            compliance_signals=_as_list("compliance_signals"),
            legal_signals=_as_list("legal_signals"),
            source_urls=_as_list("source_urls", limit=4),
            missing_materials=_as_list("missing_materials", limit=6),
            recommended_focus=_as_text("recommended_focus", limit=240),
        )

    def _merge_profile_summary(self, rule_summary: str, supplier_profile: SupplierProfileInsights) -> str:
        segments = [
            rule_summary.strip(),
            supplier_profile.company_summary.strip(),
            supplier_profile.products_services.strip(),
        ]
        merged: list[str] = []
        for segment in segments:
            if not segment:
                continue
            if segment in merged:
                continue
            merged.append(segment)
        return "?".join(merged)[:500]

    def _serialize_supplier_profile(self, supplier_profile: SupplierProfileInsights | None) -> SupplierProfileRead | None:
        if supplier_profile is None:
            return None
        return SupplierProfileRead(
            extraction_mode=supplier_profile.extraction_mode,
            confidence=supplier_profile.confidence,
            vendor_name=supplier_profile.vendor_name,
            company_summary=supplier_profile.company_summary,
            products_services=supplier_profile.products_services,
            data_involvement=supplier_profile.data_involvement,
            security_signals=list(supplier_profile.security_signals),
            compliance_signals=list(supplier_profile.compliance_signals),
            legal_signals=list(supplier_profile.legal_signals),
            source_urls=list(supplier_profile.source_urls),
            missing_materials=list(supplier_profile.missing_materials),
            recommended_focus=supplier_profile.recommended_focus,
        )

    def _validate_procurement_agent_draft(self, draft: ProcurementAgentVendorDraft) -> None:
        if not draft.vendor_name:
            raise ValueError("Vendor name is required for procurement agent review.")
        if not draft.source_platform:
            raise ValueError("Source platform is required for procurement agent review.")
        if len(draft.profile_summary) < 10:
            raise ValueError("Vendor profile summary must be at least 10 characters.")
        if len(draft.procurement_notes) < 10:
            raise ValueError("Procurement notes must be at least 10 characters.")

    def _build_procurement_agent_query(
        self,
        project: ProcurementProject,
        draft: ProcurementAgentVendorDraft,
        focus_points: str,
        supplier_profile: SupplierProfileInsights | None = None,
    ) -> str:
        lines = [
            "你是企业内部采购准入审查助手。",
            "不要把这次审查当成通用问答，请基于内部采购制度判断该供应商是否适合继续进入采购人工确认，并进一步进入法务审查。",
            "请结合内部采购制度库识别当前阻塞点、风险点、缺失材料和建议的下一步动作。",
            "",
            "项目背景：",
            f"- 项目名称：{project.title}",
            f"- 申请部门：{project.department}",
            f"- 采购类别：{project.category}",
            f"- 预算：{project.budget_amount} {project.currency}",
            f"- 采购目的：{project.summary or '未提供'}",
            f"- 业务价值：{project.business_value or '未提供'}",
            f"- 预计上线时间：{project.target_go_live_date or '未提供'}",
            f"- 数据范围：{project.data_scope or 'none'}",
            "",
            "供应商草稿：",
            f"- 供应商名称：{draft.vendor_name}",
            f"- 来源平台：{draft.source_platform}",
            f"- 来源链接：{draft.source_url or '未提供'}",
            f"- 供应商简介：{draft.profile_summary}",
            f"- 采购备注：{draft.procurement_notes}",
        ]
        if supplier_profile and any([
            supplier_profile.company_summary,
            supplier_profile.products_services,
            supplier_profile.data_involvement,
            supplier_profile.security_signals,
            supplier_profile.legal_signals,
        ]):
            lines.extend([
                "",
                "LLM 增强供应商画像：",
                f"- 提取模式：{supplier_profile.extraction_mode}",
                f"- 公司概述：{supplier_profile.company_summary or '未提供'}",
                f"- 产品/服务：{supplier_profile.products_services or '未提供'}",
                f"- 数据参与情况：{supplier_profile.data_involvement or '未识别'}",
                f"- 安全信号：{'; '.join(supplier_profile.security_signals[:3]) or '未识别'}",
                f"- 法务信号：{'; '.join(supplier_profile.legal_signals[:3]) or '未识别'}",
                f"- 建议补充材料：{'; '.join(supplier_profile.missing_materials[:4]) or '未识别'}",
            ])
        if focus_points.strip():
            lines.extend([
                "",
                "采购关注点：",
                focus_points.strip(),
            ])
        return "\n".join(lines)
        return "\n".join(lines)


    def _prepare_procurement_review_inputs(
        self,
        project: ProcurementProject,
        materials: list[ProcurementMaterialText],
        draft: ProcurementAgentVendorDraft,
        supplier_profile: SupplierProfileInsights | None = None,
    ) -> tuple[ProcurementMaterialGate, list[ProcurementRequirementCheck], SupplierDossier]:
        material_gate = self._evaluate_procurement_material_gate(materials, draft, supplier_profile=supplier_profile)
        supplier_dossier = self._build_supplier_dossier(project, materials, draft, supplier_profile=supplier_profile)
        requirement_checks = self._build_procurement_requirement_checks(
            project,
            materials,
            draft,
            supplier_dossier,
            supplier_profile=supplier_profile,
        )
        return material_gate, requirement_checks, supplier_dossier

    def _validate_procurement_agent_draft(self, draft: ProcurementAgentVendorDraft) -> None:
        if not draft.vendor_name.strip():
            raise ValueError("Vendor name is required for procurement agent review.")
        if not draft.source_url.strip():
            raise ValueError("Public source URL is required for procurement agent review.")
        if not draft.contact_email.strip():
            raise ValueError("Supplier contact email is required for procurement agent review.")
        if draft.quoted_amount <= 0:
            raise ValueError("Quoted amount is required for procurement agent review.")
        if len(draft.profile_summary.strip()) < 10:
            raise ValueError("Vendor profile summary must be at least 10 characters.")
        if len(draft.procurement_notes.strip()) < 10:
            raise ValueError("Procurement notes must be at least 10 characters.")

    def _classify_material_types(self, material: ProcurementMaterialText) -> tuple[str, ...]:
        text = f"{material.name}\n{material.text}".lower()
        matched: list[str] = []

        if any(
            token in text
            for token in [
                "营业执照",
                "统一社会信用代码",
                "法定代表人",
                "bank account",
                "tax registration",
                "audit report",
                "company name",
                "legal entity",
                "inc.",
                "ltd",
                "llc",
                "corp",
                "co., ltd",
            ]
        ):
            matched.append("supplier_identity")

        if self._find_valid_source_urls(text) or any(token in text for token in ["官网", "official site", "company website"]):
            matched.append("public_source")

        if any(
            token in text
            for token in [
                "saas",
                "software",
                "platform",
                "api",
                "integration",
                "工单",
                "客服",
                "ticket",
                "dashboard",
                "产品介绍",
                "服务说明",
                "product overview",
                "service overview",
                "whitepaper",
            ]
        ):
            matched.append("product_service")

        if any(
            token in text
            for token in [
                "报价",
                "quote",
                "pricing",
                "费用",
                "fee",
                "商业方案",
                "proposal",
                "sow",
                "poc",
                "采购说明",
            ]
        ):
            matched.append("commercial")

        if any(
            token in text
            for token in [
                "安全",
                "security",
                "iso27001",
                "soc 2",
                "soc2",
                "privacy",
                "隐",
                "penetration",
                "encryption",
                "questionnaire",
                "白皮书",
                "compliance",
                "合规",
            ]
        ):
            matched.append("security_compliance")

        if any(
            token in text
            for token in [
                "合同",
                "协议",
                "msa",
                "dpa",
                "条款",
                "审计权",
                "责任上限",
                "赔偿",
                "incident notice",
                "security incident",
                "data processing",
                "subprocessor",
                "分包",
                "子处理",
            ]
        ):
            matched.append("contract_terms")

        if self._looks_like_academic_material(material.name, material.text):
            return ("irrelevant",)
        if not matched:
            return ("irrelevant",)
        return tuple(dict.fromkeys(matched))

    def _find_valid_source_urls(self, text: str) -> tuple[str, ...]:
        found = re.findall(r"(?:https?://|ttps?://)[^\s)>\"]+", text or "")
        urls: list[str] = []
        for raw_url in found:
            url = raw_url.rstrip(".,;)]}")
            if url.startswith("ttp://") or url.startswith("ttps://"):
                url = f"h{url}"
            if self._looks_like_social_source(url) or self._looks_like_academic_source(url):
                continue
            urls.append(url)
        return tuple(dict.fromkeys(urls))

    def _looks_like_social_source(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(
            domain in host
            for domain in [
                "social.example.com",
                "douyin.com",
                "xiaohongshu.com",
                "xhslink.com",
                "bilibili.com",
                "weixin.qq.com",
                "mp.weixin.qq.com",
                "weibo.com",
                "tiktok.com",
                "instagram.com",
                "facebook.com",
            ]
        )

    def _looks_like_academic_source(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(
            domain in host
            for domain in [
                "doi.org",
                "arxiv.org",
                "sciencedirect.com",
                "springer.com",
                "ieee.org",
                "acm.org",
                "nature.com",
                "researchgate.net",
            ]
        )

    def _looks_like_academic_material(self, name: str, text: str) -> bool:
        lowered = f"{name}\n{text}".lower()
        academic_tokens = [
            "abstract",
            "keywords",
            "introduction",
            "references",
            "citation",
            "doi",
            "journal",
            "conference",
            "论文",
            "摘要",
            "参考文献",
            "基金项目",
        ]
        return sum(1 for token in academic_tokens if token in lowered) >= 2

    def _is_placeholder_vendor_name(self, vendor_name: str) -> bool:
        normalized = re.sub(r"\s+", " ", (vendor_name or "")).strip().lower()
        if len(normalized) < 3:
            return True
        if normalized in {
            "待确认供应商",
            "未确认供应商",
            "未知供应商",
            "待定供应商",
            "tbd",
            "unknown",
            "unknown vendor",
        }:
            return True
        if re.fullmatch(r"(page|document|scan|image|screenshot|file)[\s_-]*\d*", normalized):
            return True
        return any(
            token in normalized
            for token in ["待确认", "未确认", "未知", "报价", "白皮书", "合同", "协议", "paper", "report", "附件", "扫描件", "截图"]
        )

    def _looks_like_unreliable_source_platform(self, source_platform: str) -> bool:
        normalized = re.sub(r"\s+", "", (source_platform or "").strip().lower())
        if not normalized:
            return False
        return any(
            token in normalized
            for token in [
                "社交平台",
                "朋友圈",
                "短视频",
                "小红书",
                "抖音",
                "微博",
                "公众号",
                "微信",
                "转发",
                "转载",
                "合作伙伴转发",
                "social",
                "wechat",
                "weibo",
                "douyin",
                "xhs",
            ]
        )

    def _evaluate_procurement_material_gate(
        self,
        materials: list[ProcurementMaterialText],
        draft: ProcurementAgentVendorDraft,
        supplier_profile: SupplierProfileInsights | None = None,
    ) -> ProcurementMaterialGate:
        if not materials:
            return ProcurementMaterialGate(
                decision="fail",
                relevance_score=0.0,
                blocking_reasons=("No supplier materials were uploaded.",),
            )

        matched_types: list[str] = []
        valid_source_urls: list[str] = []
        irrelevant_count = 0
        academic_count = 0
        social_only_count = 0

        for material in materials:
            classified = self._classify_material_types(material)
            if classified == ("irrelevant",):
                irrelevant_count += 1
            matched_types.extend(item for item in classified if item != "irrelevant")
            if self._looks_like_academic_material(material.name, material.text):
                academic_count += 1
            urls = self._find_valid_source_urls(material.text)
            if urls:
                valid_source_urls.extend(urls)
            raw_urls = re.findall(r"https?://[^\s)>\"]+", material.text or "")
            if raw_urls and not urls:
                social_only_count += 1

        if draft.source_url and not self._looks_like_social_source(draft.source_url) and not self._looks_like_academic_source(draft.source_url):
            valid_source_urls.append(draft.source_url)
        if supplier_profile:
            for url in supplier_profile.source_urls:
                if not self._looks_like_social_source(url) and not self._looks_like_academic_source(url):
                    valid_source_urls.append(url)

        matched_types = list(dict.fromkeys(matched_types))
        valid_source_urls = list(dict.fromkeys(valid_source_urls))
        vendor_name = draft.vendor_name or (supplier_profile.vendor_name if supplier_profile else "")
        vendor_name_valid = bool(vendor_name.strip()) and not self._is_placeholder_vendor_name(vendor_name)
        subject_evidence = bool(
            vendor_name_valid
            or valid_source_urls
            or {"supplier_identity", "public_source"}.intersection(matched_types)
        )
        capability_evidence = bool({"product_service", "commercial"}.intersection(matched_types))

        blocking_reasons: list[str] = []
        if irrelevant_count == len(materials):
            blocking_reasons.append("上传内容看起来不像供应商准入材料，未识别到主体材料、官网来源或产品服务说明。")
        if academic_count == len(materials):
            blocking_reasons.append("上传内容更像论文或研究资料，不能作为供应商准入依据。")
        if self._looks_like_unreliable_source_platform(draft.source_platform) or (
            draft.source_url and self._looks_like_social_source(draft.source_url)
        ):
            blocking_reasons.append("当前来源平台更像社交平台、转发渠道或不可追溯来源，建议补充官网或正式公开来源。")
        if social_only_count == len(materials) and not valid_source_urls:
            blocking_reasons.append("当前仅识别到社交平台或不可追溯来源，不能单独作为准入依据。")
        if vendor_name.strip() and not vendor_name_valid:
            blocking_reasons.append("无法确认供应商主体身份，当前供应商名称像占位信息或待确认名称。")
        if not subject_evidence:
            blocking_reasons.append("无法确认供应商主体身份，缺少主体信息或可追溯公开来源。")
        if not capability_evidence:
            blocking_reasons.append("无法确认供应商产品或服务能力，缺少产品说明、方案或报价材料。")

        evidence_hits = 0
        evidence_hits += 1 if vendor_name_valid else 0
        evidence_hits += 1 if valid_source_urls else 0
        evidence_hits += 1 if subject_evidence else 0
        evidence_hits += 1 if capability_evidence else 0
        evidence_hits += min(len(matched_types), 4)
        relevance_score = round(min(evidence_hits / 8, 1.0), 2)

        return ProcurementMaterialGate(
            decision="pass" if not blocking_reasons else "fail",
            relevance_score=relevance_score,
            matched_material_types=tuple(matched_types),
            blocking_reasons=tuple(dict.fromkeys(blocking_reasons)),
        )

    def _build_supplier_dossier(
        self,
        project: ProcurementProject,
        materials: list[ProcurementMaterialText],
        draft: ProcurementAgentVendorDraft,
        supplier_profile: SupplierProfileInsights | None = None,
    ) -> SupplierDossier:
        combined_text = "\n\n".join(item.text for item in materials)
        vendor_name = (draft.vendor_name or (supplier_profile.vendor_name if supplier_profile else "")).strip()
        lowered = combined_text.lower()

        legal_entity = ""
        legal_match = re.search(
            r"([A-Z][A-Za-z0-9 .,&-]{2,80}(?:Ltd|Limited|LLC|Inc|Corp|Corporation|Company))",
            combined_text,
            flags=re.IGNORECASE,
        )
        if legal_match:
            legal_entity = legal_match.group(1).strip(" :;,.??")
        elif vendor_name:
            legal_entity = vendor_name

        source_urls = list(self._find_valid_source_urls(combined_text))
        if draft.source_url and draft.source_url not in source_urls and not self._looks_like_social_source(draft.source_url) and not self._looks_like_academic_source(draft.source_url):
            source_urls.append(draft.source_url)
        if supplier_profile:
            for url in supplier_profile.source_urls:
                if url not in source_urls and not self._looks_like_social_source(url) and not self._looks_like_academic_source(url):
                    source_urls.append(url)

        if any(token in lowered for token in ["saas", "cloud", "hosting", "multi-tenant"]):
            service_model = "software_saas"
        elif draft.requires_system_integration:
            service_model = "software_platform"
        elif any(token in lowered for token in ["api", "platform", "integration", "sdk"]):
            service_model = "software_platform"
        else:
            service_model = "software_or_service"

        if project.data_scope and project.data_scope != "none":
            data_access_level = project.data_scope
        elif draft.handles_company_data:
            data_access_level = "customer_data"
        elif any(token in lowered for token in ["personal information", "personal data", "customer data", "data processing", "api", "saas", "login", "account"]):
            data_access_level = "customer_data"
        else:
            data_access_level = "none"

        hosting_region = ""
        hosting_patterns = [
            ("mainland_china", r"(mainland china|china mainland|beijing region|shanghai region|cn-north|cn-east)"),
            ("china", r"(china|domestic deployment)"),
            ("singapore", r"(singapore)"),
            ("united_states", r"(united states|us-east|us-west)"),
            ("europe", r"(eu|europe|frankfurt|ireland)"),
        ]
        for label, pattern in hosting_patterns:
            if re.search(pattern, combined_text, flags=re.IGNORECASE):
                hosting_region = label
                break

        subprocessor_signal = "mentioned" if any(token in lowered for token in ["subprocessor", "subprocessors", "third-party processor", "outsourced processing"]) or draft.requires_system_integration else "not_mentioned"

        security_signal_summary: list[str] = []
        if supplier_profile:
            security_signal_summary.extend(list(supplier_profile.security_signals))
        for token, label in [
            ("iso27001", "ISO27001"),
            ("soc2", "SOC2"),
            ("soc 2", "SOC2"),
            ("penetration", "penetration testing"),
            ("encryption", "encryption capability"),
            ("incident", "security incident response"),
            ("privacy", "privacy statement"),
        ]:
            if token in lowered and label not in security_signal_summary:
                security_signal_summary.append(label)

        return SupplierDossier(
            vendor_name=vendor_name,
            legal_entity=legal_entity,
            service_model=service_model,
            source_urls=tuple(source_urls[:4]),
            data_access_level=data_access_level,
            hosting_region=hosting_region,
            subprocessor_signal=subprocessor_signal,
            security_signal_summary=tuple(security_signal_summary[:6]),
        )


    def _is_data_related_supplier(
        self,
        project: ProcurementProject,
        supplier_dossier: SupplierDossier,
        combined_text: str,
        supplier_profile: SupplierProfileInsights | None = None,
    ) -> bool:
        if (project.data_scope or "none") != "none":
            return True
        if supplier_dossier.data_access_level not in {"none", "unknown", ""}:
            return True
        lowered = combined_text.lower()
        if any(
            token in lowered
            for token in [
                "saas",
                "api",
                "customer data",
                "personal information",
                "data processing",
                "hosting",
                "cloud service",
                "宸ュ崟",
                "鐧诲綍",
                "为信息",
                "瀹㈡埛鏁版嵁",
            ]
        ):
            return True
        return bool(supplier_profile and supplier_profile.data_involvement.strip())

    def _build_procurement_requirement_checks(
        self,
        project: ProcurementProject,
        materials: list[ProcurementMaterialText],
        draft: ProcurementAgentVendorDraft,
        supplier_dossier: SupplierDossier,
        supplier_profile: SupplierProfileInsights | None = None,
    ) -> list[ProcurementRequirementCheck]:
        combined_text = "\n\n".join(item.text for item in materials)
        lowered = combined_text.lower()
        material_types = {item.name: set(self._classify_material_types(item)) for item in materials}

        def evidence_titles(predicate) -> tuple[str, ...]:
            titles = [name for name, kinds in material_types.items() if predicate(name, kinds)]
            return tuple(titles[:4])

        checks: list[ProcurementRequirementCheck] = []
        checks.append(
            ProcurementRequirementCheck(
                key="supplier_identity",
                label="供应商主体信息",
                status="pass"
                if bool(
                    supplier_dossier.legal_entity
                    or evidence_titles(lambda _n, kinds: "supplier_identity" in kinds)
                    or (draft.vendor_name and not self._is_placeholder_vendor_name(draft.vendor_name))
                )
                else "missing",
                evidence_titles=evidence_titles(lambda _n, kinds: "supplier_identity" in kinds),
                detail="需要营业执照、企业主体信息或等效主体证明材料。",
            )
        )
        checks.append(
            ProcurementRequirementCheck(
                key="service_capability",
                label="产品/服务说明",
                status="pass" if bool(draft.profile_summary.strip()) else "missing",
                evidence_titles=evidence_titles(lambda _n, kinds: "product_service" in kinds or "commercial" in kinds),
                detail="需要能说明软件/SaaS 产品能力、服务范围或报价方案的材料。",
            )
        )
        checks.append(
            ProcurementRequirementCheck(
                key="public_source",
                label="可追溯公开来源",
                status="pass" if supplier_dossier.source_urls else "missing",
                evidence_titles=evidence_titles(lambda _n, kinds: "public_source" in kinds),
                detail="至少需要官网或其他可追溯公开来源，社交平台和论文链接不能单独作为依据。",
            )
        )
        checks.append(
            ProcurementRequirementCheck(
                key="procurement_context",
                label="采购用途/商务背景",
                status="pass" if bool(project.summary.strip() or draft.procurement_notes.strip()) else "missing",
                evidence_titles=evidence_titles(lambda _n, kinds: "commercial" in kinds),
                detail="需要说明为何采购该供应商、业务场景和采购背景。",
            )
        )
        checks.append(
            ProcurementRequirementCheck(
                key="supplier_contact_email",
                label="供应商联系邮箱",
                status="pass" if bool(draft.contact_email.strip()) else "missing",
                detail="后续法务发送合同与跟进沟通至少需要一个可用的供应商联系邮箱。",
            )
        )
        checks.append(
            ProcurementRequirementCheck(
                key="commercial_quote",
                label="报价或预计合作金额",
                status="pass" if draft.quoted_amount > 0 else "missing",
                detail="需要提供报价或预计合作金额，用于判断商务可行性和预算匹配度。",
            )
        )

        data_related = self._is_data_related_supplier(project, supplier_dossier, combined_text, supplier_profile=supplier_profile)
        extra_checks = [
            (
                "security_questionnaire",
                "安全问卷或安全白皮书",
                any(token in lowered for token in ["security questionnaire", "问卷", "security whitepaper", "安全白皮书", "soc2", "iso27001"]),
                "需要安全问卷、安全白皮书或等效安全能力材料。",
            ),
            (
                "data_processing_description",
                "数据处理说明或隐私/DPA材料",
                any(token in lowered for token in ["dpa", "data processing", "privacy", "隐", "数据处理"]),
                "需要提供数据处理说明、隐私政策或 DPA 相关材料。",
            ),
            (
                "hosting_or_data_flow",
                "数据存储/部署/数据流说明",
                any(token in lowered for token in ["data flow", "deployment", "hosting", "region", "data residency", "storage location"]) or bool(supplier_dossier.hosting_region),
                "需要提供部署方式、数据流或数据存储位置说明。",
            ),
            (
                "incident_notification_commitment",
                "安全事件通知承诺",
                any(token in lowered for token in ["security incident", "incident notice", "24 hours", "24 灏忔椂", "24灏忔椂", "瀹夊叏浜嬩欢閫氱煡", "浜嬩欢閫氭姤"]),
                "需要提供安全事件通知承诺或等效条款。",
            ),
        ]
        for key, label, passed, detail in extra_checks:
            checks.append(
                ProcurementRequirementCheck(
                    key=key,
                    label=label,
                    status="pass" if passed else "missing" if data_related else "not_required",
                    required=data_related,
                    evidence_titles=evidence_titles(
                        lambda _n, kinds: "security_compliance" in kinds or "contract_terms" in kinds
                    ),
                    detail=detail,
                )
            )
        return checks

    def _derive_procurement_precheck_recommendation(
        self,
        material_gate: ProcurementMaterialGate,
        requirement_checks: list[ProcurementRequirementCheck],
    ) -> str:
        if material_gate.decision != "pass":
            return "reject_irrelevant_materials"
        return "review_ready"

    def _extract_dossier_risk_flags(self, supplier_dossier: SupplierDossier) -> list[str]:
        risk_flags: list[str] = []
        if supplier_dossier.data_access_level not in {"none", "unknown", ""} and not supplier_dossier.hosting_region:
            risk_flags.append("unknown_data_residency")
        if supplier_dossier.subprocessor_signal == "mentioned":
            risk_flags.append("unclear_subprocessor_arrangements")
        return risk_flags

    def _extract_procurement_hard_risk_flags(
        self,
        review,
        material_gate: ProcurementMaterialGate,
        supplier_dossier: SupplierDossier,
    ) -> list[str]:
        hard_flags = list(self._extract_dossier_risk_flags(supplier_dossier))
        contract_flag_set = {
            "missing_audit_rights",
            "missing_security_incident_notice",
            "missing_data_processing_terms",
            "liability_cap_weakened",
        }
        has_contract_material = "contract_terms" in set(material_gate.matched_material_types)
        for flag in self._extract_risk_flags(review):
            if flag in {"unknown_data_residency", "unclear_subprocessor_arrangements"}:
                hard_flags.append(flag)
                continue
            if flag in contract_flag_set and has_contract_material:
                hard_flags.append(flag)
        return list(dict.fromkeys(hard_flags))

    def _build_tool_call_read(
        self,
        *,
        tool_name: str,
        purpose: str,
        status: str,
        input_summary: str,
        output_summary: str,
    ) -> ToolCallRead:
        return ToolCallRead(
            tool_name=tool_name,
            purpose=purpose,
            status=status,
            input_summary=input_summary,
            output_summary=output_summary,
        )

    def _build_procurement_precheck_tool_trace(
        self,
        *,
        material_gate: ProcurementMaterialGate,
        requirement_checks: list[ProcurementRequirementCheck],
        supplier_dossier: SupplierDossier,
    ) -> list[ToolCallRead]:
        missing_required = [check.label for check in requirement_checks if check.required and check.status != "pass"]
        return [
            self._build_tool_call_read(
                tool_name="build_supplier_dossier",
                purpose="根据上传材料提炼供应商主体、服务模型、数据接触和安全画像。",
                status="success",
                input_summary=f"vendor={supplier_dossier.vendor_name or 'unknown'}",
                output_summary=(
                    f"主体={supplier_dossier.legal_entity or 'unknown'} "
                    f"服务模型={supplier_dossier.service_model or 'unknown'} "
                    f"数据级别={supplier_dossier.data_access_level}"
                ),
            ),
            self._build_tool_call_read(
                tool_name="check_material_gate",
                purpose="判断上传材料是否足够像真实供应商准入材料，可以进入正式制度审查。",
                status="success" if material_gate.decision == "pass" else "fail",
                input_summary=f"matched_types={len(material_gate.matched_material_types)}",
                output_summary=(
                    f"decision={material_gate.decision} "
                    f"relevance={material_gate.relevance_score} "
                    f"blockers={'; '.join(material_gate.blocking_reasons[:2]) or 'none'}"
                ),
            ),
            self._build_tool_call_read(
                tool_name="check_requirement_list",
                purpose="核对采购准入必备材料和数据相关补充材料是否齐备。",
                status="success" if not missing_required else "warn",
                input_summary=f"required_checks={len([check for check in requirement_checks if check.required])}",
                output_summary=(
                    "missing=" + (", ".join(missing_required[:4]) if missing_required else "none")
                ),
            ),
        ]

    def _merge_procurement_tool_trace(
        self,
        review: QueryResponse,
        *,
        material_gate: ProcurementMaterialGate,
        requirement_checks: list[ProcurementRequirementCheck],
        supplier_dossier: SupplierDossier,
    ) -> QueryResponse:
        precheck_trace = self._build_procurement_precheck_tool_trace(
            material_gate=material_gate,
            requirement_checks=requirement_checks,
            supplier_dossier=supplier_dossier,
        )
        merged_trace = [*precheck_trace, *list(review.tool_calls or [])]
        debug_summary = dict(review.debug_summary or {})
        debug_summary["tool_calls"] = [item.model_dump() for item in merged_trace]
        debug_summary["procurement_tool_trace"] = [item.model_dump() for item in merged_trace]
        debug_summary["material_gate"] = {
            "decision": material_gate.decision,
            "relevance_score": material_gate.relevance_score,
            "matched_material_types": list(material_gate.matched_material_types),
            "blocking_reasons": list(material_gate.blocking_reasons),
        }
        debug_summary["requirement_checks"] = [
            {
                "key": check.key,
                "label": check.label,
                "status": check.status,
                "required": check.required,
                "evidence_titles": list(check.evidence_titles),
                "detail": check.detail,
            }
            for check in requirement_checks
        ]
        debug_summary["supplier_dossier"] = {
            "vendor_name": supplier_dossier.vendor_name,
            "legal_entity": supplier_dossier.legal_entity,
            "service_model": supplier_dossier.service_model,
            "source_urls": list(supplier_dossier.source_urls),
            "data_access_level": supplier_dossier.data_access_level,
            "hosting_region": supplier_dossier.hosting_region,
            "subprocessor_signal": supplier_dossier.subprocessor_signal,
            "security_signal_summary": list(supplier_dossier.security_signal_summary),
        }
        review.tool_calls = merged_trace
        review.debug_summary = debug_summary
        return review

    def _attach_procurement_precheck_evidence(
        self,
        db: Session,
        *,
        review: QueryResponse,
        query: str,
        user_role: str,
        top_k: int,
    ) -> QueryResponse:
        plan = self.agent_service.llm_client.build_retrieval_plan(
            query,
            "procurement_fit_review",
            max(1, min(int(top_k), 10)),
        )
        document_hints = list(plan.get("document_hints", []))
        for hint in ("供应商准入", "供应商背景核验", "可追溯公开来源", "主体信息", "常见问答"):
            if hint not in document_hints:
                document_hints.append(hint)
        plan["document_hints"] = document_hints

        retrieved, retrieval_debug = self.agent_service.retrieval_service.retrieve(
            db,
            query=query,
            user_role=user_role,
            top_k=max(1, min(int(top_k), 10)),
            plan=plan,
        )
        citations = self.agent_service.retrieval_service.to_citations(retrieved)
        retrieval_trace = self._build_tool_call_read(
            tool_name="retrieve_procurement_knowledge",
            purpose="预检未通过时仍召回采购制度依据，供采购查看风险原因和补充方向。",
            status="success" if citations else "warn",
            input_summary=f"query={query[:80]} top_k={plan.get('top_k')}",
            output_summary=f"召回 {len(retrieved)} 个片段，生成 {len(citations)} 条引用",
        )

        merged_trace = [*list(review.tool_calls or []), retrieval_trace]
        debug_summary = dict(review.debug_summary or {})
        debug_summary["retrieval_plan"] = plan
        debug_summary["retrieval"] = retrieval_debug
        debug_summary["tool_calls"] = [item.model_dump() for item in merged_trace]
        debug_summary["procurement_tool_trace"] = [item.model_dump() for item in merged_trace]
        review.citations = citations
        review.tool_calls = merged_trace
        review.debug_summary = debug_summary
        return review

    def _finalize_procurement_tool_trace(
        self,
        review: QueryResponse,
        *,
        assessment: StructuredReviewRead,
    ) -> QueryResponse:
        merged_trace = [*list(review.tool_calls or [])]
        merged_trace.append(
            self._build_tool_call_read(
                tool_name="synthesize_procurement_decision",
                purpose="根据材料预检结果、知识证据和风险信号生成采购结构化结论。",
                status="success",
                input_summary=f"citations={len(review.citations or [])}",
                output_summary=f"recommendation={assessment.recommendation} legal_handoff={assessment.legal_handoff_recommendation}",
            )
        )
        debug_summary = dict(review.debug_summary or {})
        debug_summary["tool_calls"] = [item.model_dump() for item in merged_trace]
        debug_summary["procurement_tool_trace"] = [item.model_dump() for item in merged_trace]
        review.tool_calls = merged_trace
        review.debug_summary = debug_summary
        return review

    def _build_legal_material_tool_trace(
        self,
        db: Session,
        *,
        project: ProcurementProject,
        vendor: VendorCandidate,
    ) -> list[ToolCallRead]:
        artifacts = self.repository.list_artifacts(db, project.id)
        our_artifact = self._artifact_for_vendor(
            artifacts,
            ProcurementStage.legal_review.value,
            self.LEGAL_OUR_CONTRACT_ARTIFACT_TYPES,
            vendor.id,
        )
        counterparty_artifact = self._artifact_for_vendor(
            artifacts,
            ProcurementStage.legal_review.value,
            self.LEGAL_COUNTERPARTY_CONTRACT_ARTIFACT_TYPES,
            vendor.id,
        )
        return [
            self._build_tool_call_read(
                tool_name="load_our_contract",
                purpose="读取我方采购合同，为后续法务红线比对提供基准文本。",
                status="success" if our_artifact and our_artifact.document_id else "fail",
                input_summary=f"vendor={vendor.vendor_name}",
                output_summary=self._legal_artifact_summary(db, our_artifact, fallback_title="我方采购合同"),
            ),
            self._build_tool_call_read(
                tool_name="load_counterparty_contract",
                purpose="读取对方修改后的采购合同，为后续红线比对提供对照文本。",
                status="success" if counterparty_artifact and counterparty_artifact.document_id else "fail",
                input_summary=f"vendor={vendor.vendor_name}",
                output_summary=self._legal_artifact_summary(db, counterparty_artifact, fallback_title="对方修改后的采购合同"),
            ),
        ]

    def _legal_artifact_summary(
        self,
        db: Session,
        artifact: ProjectArtifact | None,
        *,
        fallback_title: str,
    ) -> str:
        if artifact is None:
            return f"{fallback_title} 缺失"
        if not artifact.document_id:
            return f"{artifact.title or fallback_title} 尚未绑定文件"
        document = db.get(Document, artifact.document_id)
        document_title = document.title if document else artifact.title or fallback_title
        return f"{document_title} 状态={artifact.status}"

    def _merge_legal_tool_trace(
        self,
        db: Session,
        *,
        review: QueryResponse,
        project: ProcurementProject,
        vendor: VendorCandidate,
        structured_review: StructuredReviewRead,
    ) -> QueryResponse:
        material_trace = self._build_legal_material_tool_trace(db, project=project, vendor=vendor)
        merged_trace = [*material_trace, *list(review.tool_calls or [])]
        merged_trace.append(
            self._build_tool_call_read(
                tool_name="synthesize_legal_decision",
                purpose="结合合同证据、红线依据和差异结果生成结构化法务结论。",
                status="success",
                input_summary=f"citations={len(review.citations or [])}",
                output_summary=f"recommendation={structured_review.recommendation} risk_level={structured_review.risk_level}",
            )
        )
        debug_summary = dict(review.debug_summary or {})
        debug_summary["tool_calls"] = [item.model_dump() for item in merged_trace]
        debug_summary["legal_tool_trace"] = [item.model_dump() for item in merged_trace]
        review.tool_calls = merged_trace
        review.debug_summary = debug_summary
        return review

    def _attach_legal_contract_comparison(
        self,
        db: Session,
        *,
        project: ProcurementProject,
        vendor: VendorCandidate,
        review: QueryResponse,
        contract_comparison: dict[str, object] | None = None,
    ) -> QueryResponse:
        artifacts = self.repository.list_artifacts(db, project.id)
        our_artifact = self._artifact_for_vendor(
            artifacts,
            ProcurementStage.legal_review.value,
            self.LEGAL_OUR_CONTRACT_ARTIFACT_TYPES,
            vendor.id,
        )
        counterparty_artifact = self._artifact_for_vendor(
            artifacts,
            ProcurementStage.legal_review.value,
            self.LEGAL_COUNTERPARTY_CONTRACT_ARTIFACT_TYPES,
            vendor.id,
        )
        if not our_artifact or not counterparty_artifact or not our_artifact.document_id or not counterparty_artifact.document_id:
            return review

        document_ids = [our_artifact.document_id, counterparty_artifact.document_id]
        sections = self.agent_service.retrieval_service.fetch_document_sections(db, document_ids=document_ids)
        if not sections:
            return review

        our_title = self._legal_artifact_document_title(db, our_artifact, fallback_title="我方采购合同")
        counterparty_title = self._legal_artifact_document_title(db, counterparty_artifact, fallback_title="对方修改后的采购合同")
        comparison_view = contract_comparison or self._compare_uploaded_legal_contracts(
            sections=sections,
            our_document_id=our_artifact.document_id,
            counterparty_document_id=counterparty_artifact.document_id,
            our_title=our_title,
            counterparty_title=counterparty_title,
        )

        debug_summary = dict(review.debug_summary or {})
        previous_comparison = debug_summary.get("comparison_view", {})
        if previous_comparison:
            debug_summary["retrieval_comparison_view"] = previous_comparison
            retrieval_flags = [str(item) for item in debug_summary.get("risk_flags", [])]
            if retrieval_flags:
                debug_summary["retrieval_risk_flags"] = retrieval_flags
        debug_summary["comparison_view"] = comparison_view
        debug_summary["legal_contract_documents"] = {
            "our_contract": our_title,
            "counterparty_contract": counterparty_title,
        }
        contract_flags = [str(item) for item in comparison_view.get("risk_flags", [])]
        debug_summary["risk_flags"] = list(dict.fromkeys(contract_flags))
        debug_summary["legal_contract_comparison_source"] = "uploaded_project_artifacts"

        existing_citation_keys = {(citation.document_id, citation.location) for citation in review.citations or []}
        contract_citations: list[Citation] = []
        for chunk in sections:
            if chunk.document_id not in set(document_ids):
                continue
            citation_key = (chunk.document_id, chunk.location)
            if citation_key in existing_citation_keys:
                continue
            contract_citations.append(
                Citation(
                    document_id=chunk.document_id,
                    document_title=chunk.document_title,
                    location=chunk.location,
                    snippet=chunk.content[:220],
                    score=1.0,
                    score_breakdown={"contract_compare": 1.0},
                )
            )
            existing_citation_keys.add(citation_key)
            if len(contract_citations) >= 4:
                break

        review.citations = [*contract_citations, *list(review.citations or [])][:8]
        review.debug_summary = debug_summary
        review.answer = self._build_legal_contract_final_answer(
            base_answer=review.answer,
            comparison_view=comparison_view,
            citations=review.citations,
        )
        if comparison_view.get("risk_flags"):
            review.next_action = "answer"
        return review

    def _build_uploaded_legal_contract_comparison(
        self,
        db: Session,
        *,
        project: ProcurementProject,
        vendor: VendorCandidate,
    ) -> dict[str, object]:
        artifacts = self.repository.list_artifacts(db, project.id)
        our_artifact = self._artifact_for_vendor(
            artifacts,
            ProcurementStage.legal_review.value,
            self.LEGAL_OUR_CONTRACT_ARTIFACT_TYPES,
            vendor.id,
        )
        counterparty_artifact = self._artifact_for_vendor(
            artifacts,
            ProcurementStage.legal_review.value,
            self.LEGAL_COUNTERPARTY_CONTRACT_ARTIFACT_TYPES,
            vendor.id,
        )
        if not our_artifact or not counterparty_artifact or not our_artifact.document_id or not counterparty_artifact.document_id:
            return {}
        sections = self.agent_service.retrieval_service.fetch_document_sections(
            db,
            document_ids=[our_artifact.document_id, counterparty_artifact.document_id],
        )
        if not sections:
            return {}
        return self._compare_uploaded_legal_contracts(
            sections=sections,
            our_document_id=our_artifact.document_id,
            counterparty_document_id=counterparty_artifact.document_id,
            our_title=self._legal_artifact_document_title(db, our_artifact, fallback_title="我方采购合同"),
            counterparty_title=self._legal_artifact_document_title(db, counterparty_artifact, fallback_title="对方修改后的采购合同"),
        )

    def _legal_comparison_query_lines(self, comparison_view: dict[str, object]) -> list[str]:
        lines: list[str] = []
        strict_missing = comparison_view.get("strict_missing_clauses", {})
        weakened = comparison_view.get("weakened_clauses", {})
        clause_evidence = comparison_view.get("clause_evidence", {})
        if isinstance(strict_missing, dict):
            for doc_title, clauses in list(strict_missing.items())[:2]:
                for clause in list(clauses)[:4]:
                    lines.append(f"- {doc_title} 缺失「{clause}」，需要查询该条款是否属于法务红线。")
        if isinstance(weakened, dict):
            for doc_title, clauses in list(weakened.items())[:2]:
                for clause in list(clauses)[:4]:
                    evidence = ""
                    if isinstance(clause_evidence, dict):
                        detail = clause_evidence.get(clause, {})
                        if isinstance(detail, dict):
                            evidence = str(detail.get(doc_title, ""))[:120]
                    suffix = f" 对方条款片段：{evidence}" if evidence else ""
                    lines.append(f"- {doc_title} 弱化「{clause}」，需要查询企业合同红线和处理建议。{suffix}")
        return lines[:8]

    def _build_legal_contract_final_answer(
        self,
        *,
        base_answer: str,
        comparison_view: dict[str, object],
        citations: list[Citation],
    ) -> str:
        difference_lines = self._legal_comparison_query_lines(comparison_view)
        risk_flags = [str(item) for item in comparison_view.get("risk_flags", [])]
        watch_lines: list[str] = []
        watch_clauses = comparison_view.get("watch_clauses", {})
        if isinstance(watch_clauses, dict):
            for doc_title, clauses in list(watch_clauses.items())[:2]:
                if clauses:
                    watch_lines.append(f"- {doc_title} 还存在观察项：{', '.join(list(clauses)[:4])}")
        if not difference_lines and not risk_flags:
            return base_answer
        citation_titles = list(dict.fromkeys(citation.document_title for citation in citations))
        lines = ["合同差异驱动审查结果："]
        if difference_lines:
            lines.append("识别到的关键差异：")
            lines.extend(difference_lines[:5])
        if risk_flags:
            lines.append("风险判断：")
            lines.extend(f"- {item}" for item in risk_flags[:5])
        if watch_lines:
            lines.append("补充观察项：")
            lines.extend(watch_lines[:3])
        if citation_titles:
            lines.append(f"已结合知识库依据：{'、'.join(citation_titles[:5])}。")
        lines.append("建议动作：优先要求对方恢复被删除或弱化的核心红线条款；如对方坚持修改，应由法务人工确认是否接受该偏离。")
        if base_answer:
            lines.extend(["", "RAG 召回依据摘要：", base_answer])
        return "\n".join(lines)

    def _compare_uploaded_legal_contracts(
        self,
        *,
        sections: list,
        our_document_id: str,
        counterparty_document_id: str,
        our_title: str,
        counterparty_title: str,
    ) -> dict[str, object]:
        our_text = "\n".join(chunk.content for chunk in sections if chunk.document_id == our_document_id)
        counterparty_text = "\n".join(chunk.content for chunk in sections if chunk.document_id == counterparty_document_id)
        clause_matrix: dict[str, dict[str, str]] = {}
        missing_clauses: dict[str, list[str]] = {counterparty_title: []}
        weakened_clauses: dict[str, list[str]] = {counterparty_title: []}
        blocking_clauses: dict[str, list[str]] = {counterparty_title: []}
        watch_clauses: dict[str, list[str]] = {counterparty_title: []}
        clause_evidence: dict[str, dict[str, str]] = {}
        risk_flags: list[str] = []

        for rule in self._legal_clause_rules():
            clause_name = rule["name"]
            patterns = list(rule["patterns"])
            weak_patterns = list(rule.get("weak_patterns", []))
            our_snippet = self._find_clause_snippet(our_text, patterns)
            counterparty_snippet = self._find_clause_snippet(counterparty_text, patterns)
            our_status = "存在" if our_snippet else "缺失"
            if not counterparty_snippet:
                counterparty_status = "缺失"
            elif self._has_weak_clause_signal(counterparty_snippet, weak_patterns):
                counterparty_status = "弱化"
            else:
                counterparty_status = "存在"

            if our_status == "缺失" and counterparty_status == "缺失":
                continue

            clause_matrix[clause_name] = {
                our_title: our_status,
                counterparty_title: counterparty_status,
            }
            clause_evidence[clause_name] = {
                our_title: our_snippet[:180],
                counterparty_title: counterparty_snippet[:180],
            }
            if counterparty_status == "缺失":
                missing_clauses[counterparty_title].append(clause_name)
                if rule.get("critical", True):
                    blocking_clauses[counterparty_title].append(clause_name)
                    risk_flags.append(f"{counterparty_title} 缺少「{clause_name}」红线条款，建议退回采购补充或要求对方恢复。")
                else:
                    watch_clauses[counterparty_title].append(clause_name)
            elif counterparty_status == "弱化":
                weakened_clauses[counterparty_title].append(clause_name)
                if rule.get("critical", True):
                    blocking_clauses[counterparty_title].append(clause_name)
                    risk_flags.append(f"{counterparty_title} 弱化「{clause_name}」条款，建议法务重点复核。")
                else:
                    watch_clauses[counterparty_title].append(clause_name)

        missing_clauses = {title: clauses for title, clauses in missing_clauses.items() if clauses}
        weakened_clauses = {title: clauses for title, clauses in weakened_clauses.items() if clauses}
        blocking_clauses = {title: clauses for title, clauses in blocking_clauses.items() if clauses}
        watch_clauses = {title: clauses for title, clauses in watch_clauses.items() if clauses}
        combined_gaps: dict[str, list[str]] = {}
        for title in set(missing_clauses) | set(weakened_clauses):
            combined_gaps[title] = list(dict.fromkeys([*missing_clauses.get(title, []), *weakened_clauses.get(title, [])]))

        return {
            "documents": {
                our_title: [our_text[:180]],
                counterparty_title: [counterparty_text[:180]],
            },
            "clause_matrix": clause_matrix,
            "missing_clauses": combined_gaps,
            "strict_missing_clauses": missing_clauses,
            "weakened_clauses": weakened_clauses,
            "blocking_clauses": blocking_clauses,
            "watch_clauses": watch_clauses,
            "clause_evidence": clause_evidence,
            "risk_flags": list(dict.fromkeys(risk_flags)),
        }

    @staticmethod
    def _legal_clause_rules() -> list[dict[str, object]]:
        return [
            {
                "name": "责任上限",
                "patterns": ["责任上限", "赔偿上限", "liability cap", "limitation of liability"],
                "weak_patterns": ["三个月", "3个月", "不超过三个月", "不超过3个月", "仅限", "不超过.*服务费"],
                "critical": True,
            },
            {
                "name": "赔偿责任",
                "patterns": ["赔偿", "违约责任", "indemnity", "indemnification"],
                "weak_patterns": ["不承担赔偿", "仅退还费用", "间接损失免责", "排除.*赔偿"],
                "critical": True,
            },
            {
                "name": "审计权",
                "patterns": ["审计权", "审计", "审计证明", "audit right", "audit rights"],
                "weak_patterns": ["不接受审计", "不接受.*审计", "不得审计", "仅提供自评", "仅提供.*自评", "无需提供"],
                "critical": True,
            },
            {
                "name": "数据处理",
                "patterns": ["数据处理", "个人信息", "处理目的", "跨境传输", "data processing", "dpa"],
                "weak_patterns": ["自行安排分包", "关联部署地点", "运营需要", "改变处理目的", "可.*跨境", "可.*传输"],
                "critical": True,
            },
            {
                "name": "保密义务",
                "patterns": ["保密义务", "保密信息", "confidential", "confidentiality"],
                "weak_patterns": ["无需承担保密义务", "仅尽合理努力", "可向第三方披露", "保密期限.*终止"],
                "critical": True,
            },
            {
                "name": "安全事件通知",
                "patterns": ["安全事件", "通知时限", "二十四小时", "24小时", "breach notice", "security incident"],
                "weak_patterns": ["合理可行", "尽快通知", "不承诺", "无固定", "不保证"],
                "critical": True,
            },
            {
                "name": "分包限制",
                "patterns": ["分包", "转包", "子处理", "subcontractor", "sub-processor"],
                "weak_patterns": ["自行安排分包", "无需同意", "可.*分包", "自行.*转包"],
                "critical": True,
            },
            {
                "name": "便利终止",
                "patterns": ["便利终止", "无因终止", "解除合同", "termination for convenience"],
                "weak_patterns": ["不得无故终止", "不接受便利终止", "只能.*违约.*终止", "不得提前解除合同", "除非.*违约.*解除合同"],
                "critical": True,
            },
            {
                "name": "付款条款",
                "patterns": ["付款", "发票", "payment terms", "invoice", "net 45"],
                "weak_patterns": ["预付款", "立即付款", "逾期.*高额", "四十五日", "45日"],
                "critical": False,
            },
            {
                "name": "服务水平",
                "patterns": ["服务水平", "服务赔偿", "SLA", "service level", "service credit"],
                "weak_patterns": ["不承诺.*服务水平", "不提供.*赔偿", "仅尽力"],
                "critical": False,
            },
            {
                "name": "争议解决与适用法律",
                "patterns": ["争议解决", "适用法律", "管辖法院", "governing law", "jurisdiction"],
                "weak_patterns": ["供应商所在地法院", "适用境外法律", "境外仲裁", "单方选择管辖"],
                "critical": False,
            },
        ]

    @staticmethod
    def _find_clause_snippet(text: str, patterns: list[str]) -> str:
        normalized = text or ""
        for pattern in patterns:
            lowered_text = normalized.lower()
            lowered_pattern = pattern.lower()
            index = lowered_text.find(lowered_pattern)
            if index < 0:
                continue
            start = max(0, index - 80)
            end = min(len(normalized), index + len(pattern) + 180)
            return re.sub(r"\s+", " ", normalized[start:end]).strip()
        return ""

    @staticmethod
    def _has_weak_clause_signal(snippet: str, weak_patterns: list[str]) -> bool:
        for pattern in weak_patterns:
            if ".*" not in pattern:
                if pattern.lower() in snippet.lower():
                    return True
                continue
            try:
                if re.search(pattern, snippet, re.IGNORECASE):
                    return True
            except re.error:
                if pattern.lower().replace(".*", "") in snippet.lower():
                    return True
        return False

    def _build_procurement_precheck_review(
        self,
        *,
        project: ProcurementProject,
        draft: ProcurementAgentVendorDraft,
        material_gate: ProcurementMaterialGate,
        requirement_checks: list[ProcurementRequirementCheck],
        supplier_dossier: SupplierDossier,
        supplier_profile: SupplierProfileInsights | None = None,
    ):
        missing_items = [check.label for check in requirement_checks if check.required and check.status != "pass"]
        answer_lines = [f"Supplier precheck for project {project.title} was blocked at the material gate stage."]
        if material_gate.blocking_reasons:
            answer_lines.append(f"Blocking reasons: {'; '.join(material_gate.blocking_reasons[:3])}")
        if missing_items:
            answer_lines.append(f"Missing required materials: {'; '.join(missing_items[:4])}")
        if supplier_profile and supplier_profile.missing_materials:
            answer_lines.append(f"Model-suggested missing materials: {'; '.join(supplier_profile.missing_materials[:4])}")
        debug_summary = {
            "risk_flags": [],
            "comparison_view": {"risk_flags": [], "missing_clauses": {}},
            "material_gate": {
                "decision": material_gate.decision,
                "relevance_score": material_gate.relevance_score,
                "matched_material_types": list(material_gate.matched_material_types),
                "blocking_reasons": list(material_gate.blocking_reasons),
            },
            "requirement_checks": [
                {
                    "key": check.key,
                    "label": check.label,
                    "status": check.status,
                    "required": check.required,
                    "evidence_titles": list(check.evidence_titles),
                    "detail": check.detail,
                }
                for check in requirement_checks
            ],
            "supplier_dossier": {
                "vendor_name": supplier_dossier.vendor_name,
                "legal_entity": supplier_dossier.legal_entity,
                "service_model": supplier_dossier.service_model,
                "source_urls": list(supplier_dossier.source_urls),
                "data_access_level": supplier_dossier.data_access_level,
                "hosting_region": supplier_dossier.hosting_region,
                "subprocessor_signal": supplier_dossier.subprocessor_signal,
                "security_signal_summary": list(supplier_dossier.security_signal_summary),
            },
        }
        precheck_trace = self._build_procurement_precheck_tool_trace(
            material_gate=material_gate,
            requirement_checks=requirement_checks,
            supplier_dossier=supplier_dossier,
        )
        debug_summary["tool_calls"] = [item.model_dump() for item in precheck_trace]
        debug_summary["procurement_tool_trace"] = [item.model_dump() for item in precheck_trace]
        return QueryResponse(
            session_id="",
            answer="\n".join(answer_lines),
            citations=[],
            confidence=0.0,
            trace_id=str(uuid.uuid4()),
            next_action="collect_materials",
            intent="procurement_fit_review",
            task_mode="procurement_fit_review",
            tool_calls=precheck_trace,
            debug_summary=debug_summary,
        )

    def _build_procurement_agent_query(
        self,
        project: ProcurementProject,
        draft: ProcurementAgentVendorDraft,
        focus_points: str,
        supplier_profile: SupplierProfileInsights | None = None,
        supplier_dossier: SupplierDossier | None = None,
        requirement_checks: list[ProcurementRequirementCheck] | None = None,
    ) -> str:
        dossier = supplier_dossier or SupplierDossier(vendor_name=draft.vendor_name)
        missing_items = [
            check.label
            for check in list(requirement_checks or [])
            if check.required and check.status != "pass"
        ]
        risk_signals: list[str] = []
        if draft.handles_company_data:
            risk_signals.append("是否处理公司/客户数据：是")
        else:
            risk_signals.append("是否处理公司/客户数据：否")
        if draft.requires_system_integration:
            risk_signals.append("是否需要系统对接：是")
        else:
            risk_signals.append("是否需要系统对接：否")
        if dossier.data_access_level not in {"unknown", "none", ""}:
            risk_signals.append(f"涉及数据处理：{dossier.data_access_level}")
        if dossier.hosting_region:
            risk_signals.append(f"数据存储地点：{dossier.hosting_region}")
        else:
            risk_signals.append("数据存储地点未说明")
        if dossier.subprocessor_signal not in {"", "unknown", "none"}:
            risk_signals.append(f"分包情况：{dossier.subprocessor_signal}")
        if dossier.security_signal_summary:
            risk_signals.append(f"安全信号：{', '.join(dossier.security_signal_summary[:3])}")
        elif supplier_profile and supplier_profile.security_signals:
            risk_signals.append(f"安全信号：{', '.join(supplier_profile.security_signals[:3])}")

        retrieval_focus = ["供应商准入", "供应商背景核验", "采购制度依据"]
        if draft.handles_company_data or dossier.data_access_level not in {"unknown", "none", ""}:
            retrieval_focus.extend(["第三方数据处理", "安全评审", "数据处理说明", "隐私DPA材料"])
        if draft.requires_system_integration:
            retrieval_focus.extend(["系统接入", "接口权限", "安全评审", "接入风险"])
        budget_amount = float(getattr(project, "budget_amount", 0) or 0)
        if draft.quoted_amount > 0 and budget_amount > 0 and draft.quoted_amount > budget_amount:
            retrieval_focus.extend(["预算例外", "采购审批矩阵", "超预算审批"])
        if self._looks_like_unreliable_source_platform(draft.source_platform) or (
            draft.source_url and self._looks_like_social_source(draft.source_url)
        ):
            retrieval_focus.extend(["可追溯公开来源", "供应商主体核验", "背景核验"])
        if missing_items:
            retrieval_focus.extend(["必备材料清单", "补充材料要求"])
        if any("安全" in item for item in missing_items):
            retrieval_focus.extend(["安全问卷", "安全白皮书"])
        if any("数据" in item or "DPA" in item for item in missing_items):
            retrieval_focus.extend(["数据处理说明", "数据存储部署", "数据流说明"])
        if any("事件" in item for item in missing_items):
            retrieval_focus.append("安全事件通知")

        service_summary = draft.profile_summary or (supplier_profile.company_summary if supplier_profile else "") or "未提供"
        public_source = ", ".join(dossier.source_urls) or draft.source_url or "未提供"
        lines = [
            "采购场景：",
            f"- 项目名称：{project.title}",
            f"- 采购类别：{project.category}",
            f"- 数据范围：{project.data_scope or 'none'}",
            f"- 项目摘要：{project.summary or '未提供'}",
            "",
            "供应商服务：",
            f"- 供应商名称：{dossier.vendor_name or draft.vendor_name}",
            f"- 服务类型：{dossier.service_model or '未识别'}",
            f"- 公开来源：{public_source}",
            f"- 报价/预计合作金额：{f'{draft.quoted_amount:.2f} {project.currency}' if draft.quoted_amount > 0 else '未提供'}",
            f"- 产品/服务简介：{service_summary}",
            "",
            "风险信号：",
            *[f"- {item}" for item in risk_signals[:5]],
        ]
        if missing_items:
            lines.extend(["", "缺失材料：", *[f"- {item}" for item in missing_items[:6]]])
        if focus_points.strip():
            lines.extend(["", "采购额外关注点：", focus_points.strip()])
        lines.extend(["", "检索重点：", *[f"- {item}" for item in list(dict.fromkeys(retrieval_focus))[:12]]])
        return "\n".join(lines)

    def _derive_procurement_final_recommendation(
        self,
        *,
        project: ProcurementProject,
        draft: ProcurementAgentVendorDraft,
        review,
        material_gate: ProcurementMaterialGate,
        requirement_checks: list[ProcurementRequirementCheck],
        supplier_dossier: SupplierDossier,
        supplier_profile: SupplierProfileInsights | None = None,
    ) -> str:
        precheck = self._derive_procurement_precheck_recommendation(material_gate, requirement_checks)
        if precheck != "review_ready":
            return precheck
        fit_status, _fit_detail = self._assess_procurement_business_fit(
            project=project,
            draft=draft,
            supplier_profile=supplier_profile,
            supplier_dossier=supplier_dossier,
        )
        if fit_status == "fail":
            return "needs_required_materials"
        risk_flags = self._extract_procurement_hard_risk_flags(review, material_gate, supplier_dossier)
        if risk_flags:
            return "review_with_risks"
        return "recommend_proceed"

    def _assess_procurement_business_fit(
        self,
        *,
        project: ProcurementProject,
        draft: ProcurementAgentVendorDraft,
        supplier_dossier: SupplierDossier,
        supplier_profile: SupplierProfileInsights | None = None,
    ) -> tuple[str, str]:
        project_text = " ".join(
            item
            for item in [
                project.title,
                project.category,
                project.summary,
                project.data_scope,
            ]
            if item
        )
        supplier_text = " ".join(
            item
            for item in [
                draft.profile_summary,
                draft.procurement_notes,
                supplier_dossier.service_model,
                supplier_profile.company_summary if supplier_profile else "",
                supplier_profile.products_services if supplier_profile else "",
            ]
            if item
        )

        generic_fit_tokens = {
            "软件",
            "系统",
            "平台",
            "工具",
            "流程",
            "管理",
            "业务",
            "数据",
            "报表",
            "配置",
            "任务",
            "协同",
            "审批",
            "分析",
            "能力",
            "服务",
            "项目",
            "日常",
            "支持",
            "采购",
            "供应",
            "应商",
            "供应商",
            "需要",
            "继续",
            "推进",
            "续推",
            "覆盖",
            "当前",
            "介绍",
            "关键",
            "功能",
            "专业",
            "提醒",
            "表单",
        }
        project_tokens = {token for token in tokenize_text(project_text.lower()) if len(token) >= 2}
        supplier_tokens = {token for token in tokenize_text(supplier_text.lower()) if len(token) >= 2}
        overlap = (project_tokens & supplier_tokens) - generic_fit_tokens

        software_like = {"software", "saas", "system", "platform", "系统", "平台"}
        service_model = (supplier_dossier.service_model or "").lower()
        category = (project.category or "").lower()
        software_match = category == "software" and any(token in service_model for token in software_like)

        if overlap:
            if overlap:
                matched = "、".join(sorted(list(overlap))[:4])
                fit_detail = f"供应商产品描述与当前项目需求存在直接匹配信号：{matched}。"
            else:
                fit_detail = "供应商服务形态与当前采购类别基本一致，可作为候选供应商继续推进。"
            if draft.quoted_amount > 0 and float(project.budget_amount or 0) > 0:
                budget = float(project.budget_amount or 0)
                if draft.quoted_amount > budget * 1.2:
                    return "fail", f"供应商能力初步匹配，但报价 {draft.quoted_amount:.2f} {project.currency} 明显高于项目预算 {budget:.2f} {project.currency}，当前不建议继续推进。"
                if draft.quoted_amount > budget:
                    return "warn", f"{fit_detail} 但当前报价 {draft.quoted_amount:.2f} {project.currency} 已高于项目预算 {budget:.2f} {project.currency}，建议先确认商务可行性。"
                fit_detail = f"{fit_detail} 当前报价 {draft.quoted_amount:.2f} {project.currency} 在预算范围内。"
            return "pass", fit_detail

        if not supplier_text.strip():
            return "fail", "当前缺少可用于判断需求匹配度的产品或服务说明，暂不建议直接推进。"

        if software_match:
            return "warn", "供应商属于软件或平台类服务，但当前描述没有体现和本项目核心场景的直接匹配点，建议采购要求业务补充功能对照。"

        return "warn", "已能识别供应商主体和基础能力，但与当前项目需求的直接匹配信号较弱，建议采购补充使用场景或功能对照后再确认。"

    def _build_procurement_agent_assessment(
        self,
        project: ProcurementProject,
        draft: ProcurementAgentVendorDraft,
        review,
        focus_points: str,
        supplier_profile: SupplierProfileInsights | None = None,
        material_gate: ProcurementMaterialGate | None = None,
        requirement_checks: list[ProcurementRequirementCheck] | None = None,
        supplier_dossier: SupplierDossier | None = None,
    ) -> StructuredReviewRead:
        material_gate = material_gate or ProcurementMaterialGate()
        requirement_checks = list(requirement_checks or [])
        supplier_dossier = supplier_dossier or SupplierDossier(vendor_name=draft.vendor_name)
        raw_risk_flags = self._extract_procurement_hard_risk_flags(review, material_gate, supplier_dossier)
        readable_risks = [self._risk_summary_from_flag(flag) for flag in raw_risk_flags]
        missing_items = [check.label for check in requirement_checks if check.required and check.status != "pass"]
        fit_status, fit_detail = self._assess_procurement_business_fit(
            project=project,
            draft=draft,
            supplier_profile=supplier_profile,
            supplier_dossier=supplier_dossier,
        )
        legal_handoff = self._derive_procurement_legal_handoff(
            project,
            review,
            raw_risk_flags,
            recommendation=draft.ai_recommendation,
        )

        recommendation = draft.ai_recommendation or "needs_required_materials"
        conclusion_map = {
            "reject_irrelevant_materials": "当前识别到供应商主体或来源存在明显问题，建议采购重点核实相关风险后再决定是否继续。",
            "needs_required_materials": "当前识别到若干待补充信息，建议采购补齐材料后再做人工判断。",
            "review_with_risks": "当前识别到需要重点关注的风险信号，建议采购结合制度依据进一步判断。",
            "recommend_proceed": "当前未识别到明显阻塞项，但仍建议采购结合制度依据做人工确认。",
        }
        conclusion = conclusion_map.get(recommendation, "当前材料不足以支持继续推进。")
        analysis_tags = self._build_procurement_analysis_tags(
            project=project,
            draft=draft,
            material_gate=material_gate,
            requirement_checks=requirement_checks,
            raw_risk_flags=raw_risk_flags,
            fit_status=fit_status,
        )
        blocking_issues = list(material_gate.blocking_reasons)
        if fit_status in {"warn", "fail"} and fit_detail:
            blocking_issues.append(fit_detail)
        if draft.handles_company_data and "data_handling_risk" in analysis_tags:
            blocking_issues.append("该供应商会接触公司或客户数据，需重点确认数据处理边界。")
        if draft.requires_system_integration and "system_integration_risk" in analysis_tags:
            blocking_issues.append("该供应商需要与内部系统对接，需重点确认接口、权限和实施影响。")
        fit_reason = self._build_procurement_analysis_summary(
            material_gate=material_gate,
            fit_detail=fit_detail,
            readable_risks=readable_risks,
            missing_items=missing_items,
            recommendation=recommendation,
        )
        escalation = ""
        fit_decision = ""

        check_items = [
            StructuredCheckItemRead(
                label="主体与来源是否成立",
                status="pass" if material_gate.decision == "pass" else "fail",
                detail="；".join(material_gate.blocking_reasons[:3]) if material_gate.blocking_reasons else "已识别到供应商主体、来源和基础能力材料。",
            )
        ]
        check_items.append(
            StructuredCheckItemRead(
                label="需求匹配度",
                status="pass" if fit_status == "pass" else "warn" if fit_status == "warn" else "fail",
                detail=fit_detail,
            )
        )
        for check in requirement_checks:
            check_items.append(
                StructuredCheckItemRead(
                    label=check.label,
                    status="pass" if check.status == "pass" else "warn",
                    detail=check.detail,
                )
            )
        check_items.append(
            StructuredCheckItemRead(
                label="风险分析摘要",
                status="pass" if not blocking_issues and not readable_risks else "warn",
                detail=fit_reason,
            )
        )

        open_questions: list[str] = []
        for reason in material_gate.blocking_reasons:
            open_questions.append(reason)
        for check in requirement_checks:
            if check.required and check.status != "pass":
                open_questions.append(f"补充材料：{check.label}")
        if readable_risks:
            open_questions.append(f"升级复核：{readable_risks[0]}")
        if focus_points.strip():
            open_questions.append(f"结合采购关注点继核：{focus_points.strip()}")
        if supplier_profile and supplier_profile.missing_materials:
            open_questions.extend([f"模型建补充: {item}" for item in supplier_profile.missing_materials[:2]])

        summary = fit_reason
        return StructuredReviewRead(
            review_kind="procurement_agent_review",
            conclusion=conclusion,
            recommendation=recommendation,
            summary=summary,
            analysis_tags=analysis_tags,
            fit_decision=fit_decision,
            fit_reason=fit_reason,
            missing_materials=missing_items[:6],
            escalation=escalation,
            decision_suggestion="manual_review",
            next_step=legal_handoff["next_step"],
            legal_handoff_recommendation=legal_handoff["recommendation"],
            legal_handoff_reason=legal_handoff["reason"],
            blocking_issues=list(dict.fromkeys(blocking_issues))[:6],
            check_items=check_items,
            risk_flags=readable_risks,
            open_questions=open_questions[:6],
            evidence=self._build_evidence_items(review),
        )

    def _derive_procurement_legal_handoff(
        self,
        project: ProcurementProject,
        review,
        raw_risk_flags: list[str],
        *,
        recommendation: str,
    ) -> dict[str, str]:
        if recommendation in {"reject_irrelevant_materials", "needs_required_materials"}:
            return {
                "recommendation": "wait_for_more_materials",
                "reason": "当前材料尚未通过采购准入预检，必须先补充有效材料后再决定是否转法务。",
                "next_step": "补充主体材料、产品说明和必备合规材料后重新运行审查。",
            }
        if review.next_action != "answer":
            return {
                "recommendation": "wait_for_more_materials",
                "reason": "知识库未给出足够明确的制度依据，建议先补充材料再继续。",
                "next_step": "补充证据后重新运行供应商审查。",
            }

        evidence_text = "\n".join([review.answer, *(citation.snippet for citation in list(review.citations or [])[:4])]).lower()
        escalation_terms = (
            "legal review",
            "legal approval",
            "审计权",
            "责任上限",
            "赔偿",
            "数据处理",
            "跨境",
            "个人信息",
            "security incident",
            "incident notification",
            "subprocessor",
            "分包",
            "子处理",
        )
        if raw_risk_flags or any(term in evidence_text for term in escalation_terms):
            reason = "审查结果命中了安全或法务升级信号，建议采购确认后提交法务复核。"
            if raw_risk_flags:
                reason = f"{reason} 首个风险点：{self._risk_summary_from_flag(raw_risk_flags[0])}"
            return {
                "recommendation": "suggest_legal_review",
                "reason": reason,
                "next_step": "由采购补齐相关材料后，提交法务或安全团队进一步复核。",
            }
        return {
            "recommendation": "hold_for_procurement",
            "reason": "系统未识别到必须立即升级法务的红线，可先由采购部门结合业务背景做最终确认。",
            "next_step": "采购确认供应商信息无误后，再决定是否上传给法务。",
        }

    def _procurement_missing_material_tag(self, label: str) -> str:
        mapping = {
            "供应商主体信息": "missing_subject_identity",
            "产品/服务说明": "missing_service_description",
            "可追溯公开来源": "missing_public_source",
            "采购用途/商务背景": "missing_procurement_context",
            "供应商联系邮箱": "missing_contact_email",
            "报价或预计合作金额": "missing_commercial_quote",
            "安全问卷或安全白皮书": "missing_security_materials",
            "数据处理说明或隐私/DPA材料": "missing_data_processing_materials",
            "数据存储/部署/数据流说明": "missing_hosting_details",
            "安全事件通知承诺": "missing_incident_commitment",
        }
        return mapping.get(label, f"missing_{label}".replace("/", "_").replace(" ", "_"))

    def _build_procurement_analysis_tags(
        self,
        *,
        project: ProcurementProject,
        draft: ProcurementAgentVendorDraft,
        material_gate: ProcurementMaterialGate,
        requirement_checks: list[ProcurementRequirementCheck],
        raw_risk_flags: list[str],
        fit_status: str,
    ) -> list[str]:
        tags: list[str] = []
        if material_gate.decision != "pass":
            tags.append("material_gate_failed")
        if any("主体" in reason for reason in material_gate.blocking_reasons):
            tags.append("subject_identity_gap")
        if any("来源" in reason or "社交平台" in reason for reason in material_gate.blocking_reasons):
            tags.append("source_reliability_risk")
        if any("产品" in reason or "服务能力" in reason for reason in material_gate.blocking_reasons):
            tags.append("service_capability_gap")
        if fit_status == "warn":
            tags.append("business_fit_gap")
        elif fit_status == "fail":
            tags.extend(["budget_or_fit_blocker", "manual_replacement_recommended"])
        if float(project.budget_amount or 0) > 0 and draft.quoted_amount > float(project.budget_amount or 0):
            tags.append("budget_overrun")
        if draft.handles_company_data:
            tags.append("data_handling_risk")
        if draft.requires_system_integration:
            tags.append("system_integration_risk")
        for check in requirement_checks:
            if check.required and check.status != "pass":
                tags.append(self._procurement_missing_material_tag(check.label))
        risk_flag_map = {
            "unknown_data_residency": "unknown_data_residency",
            "unclear_subprocessor_arrangements": "unclear_subprocessor_arrangements",
            "missing_audit_rights": "missing_audit_rights",
            "missing_security_incident_notice": "missing_incident_commitment",
            "missing_data_processing_terms": "missing_data_processing_materials",
            "liability_cap_weakened": "liability_cap_weakened",
            "manual_follow_up_required": "manual_follow_up_required",
        }
        for flag in raw_risk_flags:
            tags.append(risk_flag_map.get(flag, flag))
        return list(dict.fromkeys(tags))

    def _build_procurement_analysis_summary(
        self,
        *,
        material_gate: ProcurementMaterialGate,
        fit_detail: str,
        readable_risks: list[str],
        missing_items: list[str],
        recommendation: str,
    ) -> str:
        parts: list[str] = []
        if material_gate.blocking_reasons:
            parts.append(material_gate.blocking_reasons[0])
        if fit_detail:
            parts.append(fit_detail)
        if readable_risks:
            parts.append(f"重点风险：{readable_risks[0]}")
        if missing_items:
            parts.append(f"待补充：{'、'.join(missing_items[:3])}")
        if not parts:
            default_map = {
                "reject_irrelevant_materials": "当前供应商信息不足以支撑采购推进，需要采购人工确认是否更换候选供应商。",
                "needs_required_materials": "当前供应商存在待确认项，建议采购结合制度依据人工判断。",
                "review_with_risks": "当前供应商存在风险信号，建议采购结合制度依据进一步核实。",
                "recommend_proceed": "当前供应商未发现明显阻塞项，但仍建议采购结合制度依据人工判断。",
            }
            parts.append(default_map.get(recommendation, "请采购结合制度依据和当前材料做人工判断。"))
        return " ".join(part for part in parts if part).strip()

    def _build_vendor_structured_review(
        self,
        project: ProcurementProject,
        vendor: VendorCandidate,
        review,
    ) -> StructuredReviewRead:
        risk_flags = self._extract_risk_flags(review)
        conclusion = (
            "建议继续进入人工比选"
            if vendor.ai_recommendation == "recommend_proceed"
            else "建补充调查后再决定"
            if vendor.ai_recommendation == "needs_follow_up"
            else "存在风险，需谨慎评估"
        )
        open_questions = self._vendor_open_questions(project, vendor, review)
        return StructuredReviewRead(
            review_kind="vendor_onboarding",
            conclusion=conclusion,
            recommendation=vendor.ai_recommendation or "needs_follow_up",
            summary=review.answer,
            check_items=[
                StructuredCheckItemRead(
                    label="Supplier baseline information",
                    status="pass" if vendor.profile_summary or vendor.source_url else "warn",
                    detail="Source information or supplier summary is available." if vendor.profile_summary or vendor.source_url else "Please add a public source link or supplier summary.",
                ),
                StructuredCheckItemRead(
                    label="Onboarding recommendation",
                    status="pass" if vendor.ai_recommendation == "recommend_proceed" else "warn" if vendor.ai_recommendation == "needs_follow_up" else "fail",
                    detail=conclusion,
                ),
                StructuredCheckItemRead(
                    label="Data and compliance risks",
                    status="fail" if risk_flags else "pass",
                    detail="; ".join(risk_flags[:3]) if risk_flags else "No structured data or compliance risk flags were detected.",
                ),
            ],
            risk_flags=risk_flags,
            open_questions=open_questions,
            evidence=self._build_evidence_items(review),
        )

    def _build_legal_structured_review(
        self,
        project: ProcurementProject,
        vendor: VendorCandidate,
        review,
    ) -> StructuredReviewRead:
        risk_flags = self._extract_risk_flags(review)
        blocking_risk_flags = [flag for flag in risk_flags if flag != "manual_follow_up_required"]
        watch_risk_flags = [flag for flag in risk_flags if flag == "manual_follow_up_required"]
        comparison_view = review.debug_summary.get("comparison_view", {}) if isinstance(review.debug_summary, dict) else {}
        blocking_clauses = comparison_view.get("blocking_clauses", {}) if isinstance(comparison_view, dict) else {}
        watch_clauses = comparison_view.get("watch_clauses", {}) if isinstance(comparison_view, dict) else {}
        blocking_details: list[str] = []
        watch_details: list[str] = []
        for doc_title, clauses in list(blocking_clauses.items())[:2]:
            if clauses:
                blocking_details.append(f"{doc_title} 存在关键条款风险：{', '.join(clauses[:4])}")
        for doc_title, clauses in list(watch_clauses.items())[:2]:
            if clauses:
                watch_details.append(f"{doc_title} 存在观察项：{', '.join(clauses[:4])}")
        clause_details = [*blocking_details, *watch_details]
        recommendation = "review_with_risks" if (blocking_risk_flags or blocking_details) else "recommend_proceed"
        if watch_details and recommendation == "recommend_proceed":
            recommendation = "needs_follow_up"
        if watch_risk_flags and recommendation == "recommend_proceed":
            recommendation = "needs_follow_up"
        if not review.citations and recommendation == "recommend_proceed":
            recommendation = "needs_follow_up"
        if blocking_risk_flags or blocking_details:
            risk_level = "high"
        elif watch_details or watch_risk_flags or not review.citations or review.next_action != "answer":
            risk_level = "medium"
        else:
            risk_level = "low"
        decision_suggestion = "return" if recommendation == "review_with_risks" else "approve"
        blocking_issues = list(blocking_details)
        if not review.citations:
            blocking_issues.append("当前缺少足够条款引用，建议法务谨慎复核。")
        if review.next_action != "answer":
            blocking_issues.append("模型未形成完全确定结论，建议结合人工判断。")
        summary = review.answer or ("发现合同红线风险，建议退回采购处理。" if decision_suggestion == "return" else "两份合同已完成初步红线审查。")
        if clause_details:
            summary = f"{summary}\n\n合同红线差异摘要：{'；'.join(clause_details[:3])}"
        return StructuredReviewRead(
            review_kind="legal_contract_review",
            conclusion="发现合同红线风险，建议退回采购处理" if decision_suggestion == "return" else "合同可进入人工法务决策",
            recommendation=recommendation,
            summary=summary,
            risk_level=risk_level,
            decision_suggestion=decision_suggestion,
            clause_gaps=clause_details,
            blocking_issues=blocking_issues[:6],
            next_step="法务确认结论后，可直接通过或退回采购。" if decision_suggestion == "approve" else "建议退回采购修订条款或重新处理供应商合同。",
            check_items=[
                StructuredCheckItemRead(
                    label="合同材料齐备",
                    status="pass",
                    detail=f"已将 {vendor.vendor_name} 的我方采购合同与对方修改版合同纳入审查。",
                ),
                StructuredCheckItemRead(
                    label="红线条款差异",
                    status="fail" if blocking_details else "warn" if watch_details else "pass",
                    detail="；".join(clause_details[:2]) if clause_details else "未识别到明确的红线条款缺失或弱化。",
                ),
                StructuredCheckItemRead(
                    label="法务建议动作",
                    status="fail" if decision_suggestion == "return" else "warn" if recommendation == "needs_follow_up" else "pass",
                    detail="建议退回采购处理当前合同风险。"
                    if decision_suggestion == "return"
                    else "建议法务复核观察项后再决定是否通过。"
                    if recommendation == "needs_follow_up"
                    else "可进入法务人工通过判断。",
                ),
            ],
            risk_flags=risk_flags,
            open_questions=self._legal_open_questions(review, clause_details),
            evidence=self._build_evidence_items(review),
        )

    def _extract_risk_flags(self, review) -> list[str]:
        debug_summary = review.debug_summary or {}
        risk_flags = list(debug_summary.get("risk_flags", []))
        comparison_view = debug_summary.get("comparison_view")
        if isinstance(comparison_view, dict):
            risk_flags.extend(comparison_view.get("risk_flags", []))
        if not risk_flags and review.next_action != "answer":
            risk_flags.append("manual_follow_up_required")
        return list(dict.fromkeys(str(flag) for flag in risk_flags))

    def _build_evidence_items(self, review) -> list[StructuredEvidenceRead]:
        return [
            StructuredEvidenceRead(
                document_title=citation.document_title,
                location=citation.location,
                snippet=citation.snippet,
            )
            for citation in list(review.citations or [])[:4]
        ]

    def _vendor_open_questions(self, project: ProcurementProject, vendor: VendorCandidate, review) -> list[str]:
        questions: list[str] = []
        if not vendor.source_url:
            questions.append("补充供应商官网或第三方平台链接。")
        if not vendor.profile_summary:
            questions.append("补充供应商业务能力与准入资料摘要。")
        if project.data_scope != "none":
            questions.append("补充供应商数据处理、存储与安全事件响应说明。")
        if review.next_action != "answer":
            questions.append("当前证据不足，建议继续收集公开信息或准入材料。")
        return questions[:4]

    def _legal_open_questions(self, review, clause_details: list[str]) -> list[str]:
        questions: list[str] = []
        if clause_details:
            questions.append("逐条确认缺失或弱化条款是否可接受。")
        if review.next_action != "answer":
            questions.append("补充标准模板或对方回传合同中的缺失证据。")
        if not review.citations:
            questions.append("当前缺少足够条款证据，建议重新上传合同材料。")
        return questions[:4]

    def _structured_review_from_json(self, raw_json: str) -> StructuredReviewRead | None:
        if not raw_json:
            return None
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            return None
        if not payload:
            return None
        return StructuredReviewRead.model_validate(payload)

    def _latest_legal_review(self, decisions: list) -> StructuredReviewRead | None:
        for decision in decisions:
            if decision.decision_type == "legal_ai_review":
                return self._structured_review_from_json(decision.structured_summary_json)
        return None

    def _artifact_for_vendor(
        self,
        artifacts: list[ProjectArtifact],
        stage: str,
        artifact_type: str | tuple[str, ...],
        linked_vendor_id: str,
    ) -> ProjectArtifact | None:
        artifact_types = {artifact_type} if isinstance(artifact_type, str) else set(artifact_type)
        fallback: ProjectArtifact | None = None
        for artifact in artifacts:
            if artifact.stage != stage or artifact.artifact_type not in artifact_types:
                continue
            if linked_vendor_id and artifact.linked_vendor_id not in {"", linked_vendor_id}:
                continue
            if artifact.status in {"provided", "approved"}:
                return artifact
            if fallback is None:
                fallback = artifact
        return fallback

    def _build_legal_handoff(
        self,
        project: ProcurementProject,
        vendors: list[VendorCandidate],
        artifacts: list[ProjectArtifact],
    ) -> LegalHandoffRead | None:
        if not project.selected_vendor_id:
            return None
        vendor = next((item for item in vendors if item.id == project.selected_vendor_id), None)
        if vendor is None:
            return None
        dispatch_artifact = self._artifact_for_vendor(
            artifacts,
            ProcurementStage.legal_review.value,
            self.LEGAL_OUR_CONTRACT_ARTIFACT_TYPES,
            vendor.id,
        )
        redline_artifact = self._artifact_for_vendor(
            artifacts,
            ProcurementStage.legal_review.value,
            self.LEGAL_COUNTERPARTY_CONTRACT_ARTIFACT_TYPES,
            vendor.id,
        )
        return LegalHandoffRead(
            vendor_id=vendor.id,
            vendor_name=vendor.vendor_name,
            contact_name=vendor.contact_name,
            contact_email=vendor.contact_email,
            contact_phone=vendor.contact_phone,
            source_url=vendor.source_url,
            our_contract_status=dispatch_artifact.status if dispatch_artifact else "missing",
            our_contract_notes=dispatch_artifact.notes if dispatch_artifact else "",
            counterparty_contract_status=redline_artifact.status if redline_artifact else "missing",
            counterparty_contract_notes=redline_artifact.notes if redline_artifact else "",
            standard_contract_status=dispatch_artifact.status if dispatch_artifact else "missing",
            standard_contract_notes=dispatch_artifact.notes if dispatch_artifact else "",
            vendor_redline_status=redline_artifact.status if redline_artifact else "missing",
            vendor_redline_notes=redline_artifact.notes if redline_artifact else "",
            ready_for_legal_review=bool(
                dispatch_artifact
                and redline_artifact
                and dispatch_artifact.status in {"provided", "approved"}
                and redline_artifact.status in {"provided", "approved"}
            ),
        )

    def _serialize_summary(self, db: Session, project: ProcurementProject) -> ProjectSummaryRead:
        return ProjectSummaryRead(
            id=project.id,
            title=project.title,
            requester_name=project.requester_name,
            department=project.department,
            vendor_name=project.vendor_name,
            selected_vendor_id=project.selected_vendor_id,
            category=project.category,
            budget_amount=project.budget_amount,
            currency=project.currency,
            current_stage=project.current_stage,
            risk_level=project.risk_level,
            status=project.status,
            current_owner_role=project.current_owner_role,
            open_task_count=self.repository.count_open_tasks(db, project.id),
            open_risk_count=self.repository.count_open_risks(db, project.id),
            vendor_count=self.repository.count_vendors(db, project.id),
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    def _redact_summary_for_user(self, summary: ProjectSummaryRead, current_user: UserProfileRead) -> ProjectSummaryRead:
        if current_user.role in {"procurement", "legal", "admin"}:
            return summary
        payload = summary.model_dump()
        payload["vendor_count"] = 1 if summary.selected_vendor_id else 0
        return ProjectSummaryRead.model_validate(payload)

    def _allowed_actions(self, project: ProcurementProject, viewer_role: str) -> list[str]:
        if project.status == "cancelled":
            return []
        mapping: dict[str, dict[str, list[str]]] = {
            ProcurementStage.business_draft.value: {
                "business": ["update", "submit", "cancel"],
            },
            ProcurementStage.manager_review.value: {
                "business": ["withdraw"],
                "manager": ["manager_approve", "manager_return", "cancel"],
            },
            ProcurementStage.procurement_sourcing.value: {
                "procurement": ["add_vendor", "review_vendor", "select_vendor", "cancel"],
            },
            ProcurementStage.legal_review.value: {
                "legal": ["review_legal", "legal_approve", "return_to_procurement", "cancel"],
            },
            ProcurementStage.final_approval.value: {
                "manager": ["final_approve", "final_return_legal", "final_return_procurement", "cancel"],
                "admin": ["sign", "cancel"],
            },
            ProcurementStage.signing.value: {
                "admin": ["sign", "cancel"],
            },
            ProcurementStage.completed.value: {
                "admin": [],
            },
        }
        return mapping.get(project.current_stage, {}).get(viewer_role, [])

    def _redact_detail_for_user(self, detail: ProjectDetailRead, current_user: UserProfileRead) -> ProjectDetailRead:
        if current_user.role == "admin":
            payload = detail.model_dump()
            payload["allowed_actions"] = self._allowed_actions(detail, current_user.role)
            return ProjectDetailRead(**payload)

        payload = detail.model_dump()
        payload["allowed_actions"] = self._allowed_actions(detail, current_user.role)
        payload["archives"] = []

        if current_user.role == "business":
            payload["vendors"] = []
            payload["artifacts"] = [artifact for artifact in payload["artifacts"] if artifact["stage"] in {"business_draft", "manager_review"}]
            payload["risks"] = []
            payload["legal_handoff"] = None
            payload["decisions"] = [
                decision
                for decision in payload["decisions"]
                if decision["decision_type"] in {"draft_update", "submit", "withdraw", "manager_review", "final_approval", "cancel"}
            ]
            payload["latest_legal_review"] = None
        elif current_user.role == "manager":
            payload["vendors"] = [
                vendor
                for vendor in payload["vendors"]
                if not detail.selected_vendor_id or vendor["id"] == detail.selected_vendor_id
            ]
            payload["artifacts"] = [
                artifact
                for artifact in payload["artifacts"]
                if artifact["artifact_type"]
                not in {
                    "standard_contract_dispatch",
                    "vendor_redline_contract",
                    "our_procurement_contract",
                    "counterparty_redline_contract",
                }
            ]
            payload["legal_handoff"] = None
        elif current_user.role == "legal":
            payload["vendors"] = [
                vendor
                for vendor in payload["vendors"]
                if not detail.selected_vendor_id or vendor["id"] == detail.selected_vendor_id
            ]

        if current_user.role in {"business", "manager"}:
            for vendor in payload["vendors"]:
                vendor["procurement_notes"] = ""
                vendor["source_url"] = ""
                vendor["ai_review_trace_id"] = ""
            for risk in payload["risks"]:
                risk["trace_id"] = ""
            for decision in payload["decisions"]:
                decision["trace_id"] = ""
        if current_user.role != "admin":
            for vendor in payload["vendors"]:
                vendor["ai_review_trace_id"] = ""
            for risk in payload["risks"]:
                risk["trace_id"] = ""
            for decision in payload["decisions"]:
                decision["trace_id"] = ""

        return ProjectDetailRead.model_validate(payload)

    def _serialize_detail(
        self,
        project: ProcurementProject,
        tasks: list[ProjectTask],
        vendors: list[VendorCandidate],
        artifacts: list[ProjectArtifact],
        risks: list[ProjectRisk],
        decisions: list,
        stages: list[ProjectStageRecord],
        archives: list[ProjectArchiveSnapshot],
        blockers: list[str],
    ) -> ProjectDetailRead:
        latest_legal_review = self._latest_legal_review(decisions)
        procurement_material_session = self._procurement_material_session_from_json(project.procurement_materials_json)
        legal_handoff = self._build_legal_handoff(project, vendors, artifacts)
        return ProjectDetailRead(
            id=project.id,
            title=project.title,
            requester_name=project.requester_name,
            department=project.department,
            vendor_name=project.vendor_name,
            selected_vendor_id=project.selected_vendor_id,
            category=project.category,
            budget_amount=project.budget_amount,
            currency=project.currency,
            summary=project.summary,
            business_value=project.business_value,
            target_go_live_date=project.target_go_live_date,
            data_scope=project.data_scope,
            current_stage=project.current_stage,
            risk_level=project.risk_level,
            status=project.status,
            current_owner_role=project.current_owner_role,
            chat_session_id=project.chat_session_id,
            draft_editable=project.current_stage == ProcurementStage.business_draft.value and project.status == "active",
            allowed_actions=self._allowed_actions(project, project.current_owner_role),
            application_form_ready=self._application_form_ready(project),
            application_form_summary=self._application_form_summary(project),
            application_checks=self._build_application_checks(project),
            procurement_material_session=procurement_material_session,
            latest_legal_review=latest_legal_review,
            legal_handoff=legal_handoff,
            blocker_summary=blockers,
            tasks=[ProjectTaskRead.model_validate(task) for task in tasks],
            vendors=[self._serialize_vendor(vendor) for vendor in vendors],
            artifacts=[ProjectArtifactRead.model_validate(artifact) for artifact in artifacts],
            risks=[ProjectRiskRead.model_validate(risk) for risk in risks],
            decisions=[self._serialize_decision(decision) for decision in decisions],
            stages=[ProjectStageRecordRead.model_validate(stage) for stage in stages],
            archives=[ProjectArchiveSnapshotRead.model_validate(archive) for archive in archives],
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    def _serialize_vendor(self, vendor: VendorCandidate) -> VendorCandidateRead:
        payload = VendorCandidateRead.model_validate(vendor).model_dump()
        payload["structured_review"] = self._structured_review_from_json(vendor.ai_review_json)
        return VendorCandidateRead(**payload)

    def _serialize_decision(self, decision) -> ProjectDecisionRead:
        payload = ProjectDecisionRead.model_validate(decision).model_dump()
        payload["structured_summary"] = self._structured_review_from_json(decision.structured_summary_json)
        return ProjectDecisionRead(**payload)

