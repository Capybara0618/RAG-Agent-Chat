from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.entities import (
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
from app.schemas.chat import QueryRequest
from app.schemas.project import (
    ProcurementAgentExtractResult,
    ProcurementMaterialRead,
    ProcurementAgentReviewRequest,
    ProcurementAgentReviewResult,
    ProjectArchiveSnapshotRead,
    ProjectArtifactCreate,
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
    profile_summary: str = ""
    procurement_notes: str = ""
    ai_recommendation: str = ""


@dataclass(frozen=True)
class ProcurementMaterialText:
    name: str
    source_type: str
    text: str


class ProjectService:
    STAGE_ORDER = [
        ProcurementStage.business_draft.value,
        ProcurementStage.manager_review.value,
        ProcurementStage.procurement_sourcing.value,
        ProcurementStage.legal_review.value,
        ProcurementStage.final_approval.value,
        ProcurementStage.signing.value,
        ProcurementStage.completed.value,
    ]

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
                ("contract", "向目标供应商发送我方采购合同", "legal"),
                ("contract", "审查对方回传合同并确认合法合规", "legal"),
            ],
            required_artifacts=[
                ("standard_contract_dispatch", "我方采购合同已发送", "outbound"),
                ("vendor_redline_contract", "对方回传修改合同", "inbound"),
            ],
        ),
        ProcurementStage.final_approval.value: StageBlueprint(
            stage=ProcurementStage.final_approval,
            owner_role="manager",
            required_tasks=[
                ("approval", "完成最终审批并确认项目落地", "executive"),
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

    def __init__(self, *, repository: ProjectRepository, agent_service: KnowledgeOpsAgentService) -> None:
        self.repository = repository
        self.agent_service = agent_service

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
                profile_summary=payload.summary,
                procurement_notes="业务发起时录入的候选供应商。",
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
                department="客户服务中心",
                vendor_name="AlphaDesk",
                category="customer-support-saas",
                budget_amount=1200000,
                currency="CNY",
                summary="客户服务中心计划采购在线客服与工单协同 SaaS，供应商将处理客户聊天记录与工单附件，需要经过业务申请、上级审批、采购比选、法务审查、最终审批和签署归档。",
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
                profile_summary="备选客服 SaaS 供应商，价格更低但合同条款较弱。",
                procurement_notes="演示项目自动附带的备选供应商。",
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
        self._sync_business_draft_form_state(db, project)
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
                summary="上级审批通过，进入采购比选。",
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
            profile_summary=payload.profile_summary,
            procurement_notes=payload.procurement_notes,
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
        if not uploaded_files:
            raise ValueError("Please upload at least one supplier material file.")

        parser = DocumentParser()
        materials: list[ProcurementMaterialText] = []
        for file_name, content in uploaded_files:
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
                )
            )
        if not materials:
            raise ValueError("Uploaded files could not be parsed into usable supplier text.")

        draft, summary, warnings = self._extract_vendor_draft_from_materials(project, materials, current_user)
        return ProcurementAgentExtractResult(
            vendor_draft=VendorCandidateCreate(
                vendor_name=draft.vendor_name,
                source_platform=draft.source_platform,
                source_url=draft.source_url,
                profile_summary=draft.profile_summary,
                procurement_notes=draft.procurement_notes,
            ),
            extraction_summary=summary,
            extracted_materials=[
                ProcurementMaterialRead(
                    name=item.name,
                    source_type=item.source_type,
                    char_count=len(item.text),
                    excerpt=item.text[:180],
                )
                for item in materials
            ],
            warnings=warnings,
        )

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
        draft = ProcurementAgentVendorDraft(
            vendor_name=payload.vendor_name.strip(),
            source_platform=payload.source_platform.strip(),
            source_url=payload.source_url.strip(),
            profile_summary=payload.profile_summary.strip(),
            procurement_notes=payload.procurement_notes.strip(),
        )
        self._validate_procurement_agent_draft(draft)
        generated_query = self._build_procurement_agent_query(project, draft, payload.focus_points)
        review = self.agent_service.query(
            db,
            QueryRequest(
                query=generated_query,
                session_id=None,
                user_role=current_user.role,
                top_k=payload.top_k,
            ),
            current_user=current_user,
        )
        reviewed_draft = ProcurementAgentVendorDraft(
            vendor_name=draft.vendor_name,
            source_platform=draft.source_platform,
            source_url=draft.source_url,
            profile_summary=draft.profile_summary,
            procurement_notes=draft.procurement_notes,
            ai_recommendation=self._derive_ai_recommendation(review.next_action, review.debug_summary),
        )
        assessment = self._build_procurement_agent_assessment(project, reviewed_draft, review, payload.focus_points)
        return ProcurementAgentReviewResult(
            review=review,
            assessment=assessment,
            generated_query=generated_query,
        )

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

    def legal_review(self, db: Session, project_id: str, payload: ProjectLegalReviewRequest) -> ProjectLegalReviewResult:
        project = self._require_project(db, project_id)
        self._require_stage(project, ProcurementStage.legal_review.value)
        selected_vendor = self._require_selected_vendor(db, project)
        self._ensure_legal_review_artifacts_ready(db, project)
        review = self.agent_service.query(
            db,
            QueryRequest(
                query=payload.query,
                session_id=project.chat_session_id or None,
                user_role=payload.user_role,
                top_k=payload.top_k,
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
        project.chat_session_id = review.session_id
        structured_review = self._build_legal_structured_review(project, selected_vendor, review)
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
        project.risk_level = self._derive_risk_level(risks, review.next_action)
        self._refresh_active_stage_blocking_reason(db, project)
        db.commit()
        return ProjectLegalReviewResult(
            project=self.get_project_detail(db, project.id),
            review=review,
            assessment=structured_review,
            risks=[ProjectRiskRead.model_validate(risk) for risk in risks],
        )

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
                summary="法务审查通过，提交最终审批。",
                reason=payload.reason,
            )
            self._move_project_to_stage(
                db,
                project=project,
                target_stage=ProcurementStage.final_approval.value,
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
                summary="法务审查不通过，退回采购重新筛选供应商。",
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
            summary="最终审批已通过，进入签署归档。",
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
            summary=f"最终审批退回到 {payload.target_stage}。",
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
        if project.current_stage == ProcurementStage.manager_review.value and current_user.role == "business":
            allowed_roles.add("business")
        if current_user.role not in allowed_roles:
            raise PermissionError("Current account cannot edit tasks or materials in this stage.")

    def _stage_index(self, stage: str) -> int:
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
                    profile_summary=project.summary,
                    procurement_notes="业务草稿更新时同步的初始候选供应商。",
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
            business_input_vendor.manual_reason = "业务草稿中已移除初始候选供应商。"

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
                label="已填写项目名称",
                checked=bool(project.title.strip()),
                detail="项目名称已填写。" if project.title.strip() else "请填写采购项目名称。",
            ),
            RequirementCheckRead(
                key="requester",
                label="已填写申请部门与申请人",
                checked=bool(project.requester_name.strip()) and bool(project.department.strip()),
                detail="申请部门与申请人已填写。"
                if project.requester_name.strip() and project.department.strip()
                else "请补充申请人和所属部门。",
            ),
            RequirementCheckRead(
                key="purpose",
                label="已说明采购目的与需求要点",
                checked=bool(project.summary.strip()),
                detail="采购目的与需求要点已填写。" if project.summary.strip() else "请说明采购目的、采购内容和业务场景。",
            ),
            RequirementCheckRead(
                key="budget",
                label="已填写预算金额",
                checked=project.budget_amount > 0,
                detail="预算金额已填写。" if project.budget_amount > 0 else "请填写大于 0 的预算金额。",
            ),
            RequirementCheckRead(
                key="business_value",
                label="已说明业务价值",
                checked=bool(project.business_value.strip()),
                detail="业务价值已填写。" if project.business_value.strip() else "请补充预期收益或业务价值。",
            ),
            RequirementCheckRead(
                key="target_go_live_date",
                label="已填写期望上线时间",
                checked=bool(project.target_go_live_date.strip()),
                detail="期望上线时间已填写。" if project.target_go_live_date.strip() else "请填写期望上线时间。",
            ),
            RequirementCheckRead(
                key="data_scope",
                label="已识别数据范围",
                checked=bool(project.data_scope.strip()),
                detail="数据范围已标记。" if project.data_scope.strip() else "请明确是否涉及敏感数据或客户数据。",
            ),
        ]

    def _application_form_ready(self, project: ProcurementProject) -> bool:
        return all(item.checked for item in self._build_application_checks(project))

    def _application_form_summary(self, project: ProcurementProject) -> str:
        checks = self._build_application_checks(project)
        passed_count = sum(1 for item in checks if item.checked)
        total_count = len(checks)
        if passed_count == total_count:
            return f"采购申请表已完成系统校验，{passed_count}/{total_count} 项要点已满足，可由业务部门自主提交到上级审批。"
        return f"采购申请表当前已满足 {passed_count}/{total_count} 项要点，补齐未完成项后即可提交到上级审批。"

    def _sync_business_draft_form_state(self, db: Session, project: ProcurementProject) -> None:
        if project.current_stage != ProcurementStage.business_draft.value:
            return
        self._ensure_stage_defaults(db, project, ProcurementStage.business_draft.value)
        form_ready = self._application_form_ready(project)
        summary = self._application_form_summary(project)
        for task in self.repository.list_tasks(db, project.id):
            if task.stage != ProcurementStage.business_draft.value or task.title != "填写并确认采购申请表":
                continue
            task.details = "系统内置采购申请表，状态随业务字段完整度自动更新。"
            task.status = "done" if form_ready else "pending"
        for artifact in self.repository.list_artifacts(db, project.id):
            if artifact.stage != ProcurementStage.business_draft.value or artifact.artifact_type != "procurement_application_form":
                continue
            artifact.direction = "internal"
            artifact.version_no = 1
            artifact.notes = summary
            artifact.status = "provided" if form_ready else "missing"

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
                    blockers.append(f"采购申请表未完成：{item.label}")
            return blockers
        for task in tasks:
            if task.stage == current_stage and task.required and task.status != "done":
                blockers.append(f"Task pending: {task.title}")
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
            if not self._has_stage_artifact(artifacts, current_stage, "standard_contract_dispatch", project.selected_vendor_id):
                blockers.append("Legal stage requires the outbound company contract.")
            if not self._has_stage_artifact(artifacts, current_stage, "vendor_redline_contract", project.selected_vendor_id):
                blockers.append("Legal stage requires the vendor redline contract.")
        if current_stage == ProcurementStage.final_approval.value and not project.selected_vendor_id:
            blockers.append("Final approval requires a selected vendor.")
        return blockers

    def _has_stage_artifact(self, artifacts: list[ProjectArtifact], stage: str, artifact_type: str, linked_vendor_id: str) -> bool:
        for artifact in artifacts:
            if artifact.stage != stage or artifact.artifact_type != artifact_type:
                continue
            if linked_vendor_id and artifact.linked_vendor_id not in {"", linked_vendor_id}:
                continue
            if artifact.status in {"provided", "approved"}:
                return True
        return False

    def _ensure_legal_review_artifacts_ready(self, db: Session, project: ProcurementProject) -> None:
        artifacts = self.repository.list_artifacts(db, project.id)
        if not self._has_stage_artifact(
            artifacts,
            ProcurementStage.legal_review.value,
            "standard_contract_dispatch",
            project.selected_vendor_id,
        ):
            raise ValueError("Legal review requires the outbound company contract artifact.")
        if not self._has_stage_artifact(
            artifacts,
            ProcurementStage.legal_review.value,
            "vendor_redline_contract",
            project.selected_vendor_id,
        ):
            raise ValueError("Legal review requires the vendor redline contract artifact.")

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
        compare_summary = debug_summary.get("compare_summary")
        if isinstance(compare_summary, dict):
            risk_flags.extend(compare_summary.get("risk_flags", []))
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
        compare_summary = debug_summary.get("compare_summary")
        if isinstance(compare_summary, dict):
            risk_flags.extend(compare_summary.get("risk_flags", []))
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
            "manual_follow_up_required": "Evidence is not strong enough for automatic progression and needs manual review.",
        }
        return mapping.get(flag, f"Review flagged risk: {flag.replace('_', ' ')}.")

    def _risk_severity_from_flag(self, flag: str) -> str:
        if flag in {"missing_audit_rights", "missing_data_processing_terms", "liability_cap_weakened"}:
            return "high"
        if flag in {"missing_security_incident_notice", "manual_follow_up_required"}:
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
    ) -> tuple[ProcurementAgentVendorDraft, str, list[str]]:
        combined_text = "\n\n".join(item.text for item in materials)
        urls = re.findall(r"https?://[^\s)>\"]+", combined_text)
        vendor_name = self._extract_vendor_name(combined_text, materials)
        source_url = urls[0] if urls else ""
        source_platform = self._extract_source_platform(source_url, materials)
        profile_summary = self._extract_profile_summary(combined_text)
        procurement_notes = self._build_procurement_notes(project, materials, combined_text, current_user)
        warnings: list[str] = []

        if not vendor_name:
            warnings.append("未能稳定识别供应商名称，建议人工补充。")
            vendor_name = materials[0].name.rsplit(".", 1)[0][:60]
        if not source_url:
            warnings.append("材料中未识别出明确来源链接，建议补充官网或第三方平台链接。")
        if len(profile_summary) < 20:
            warnings.append("可提取的供应商简介较少，建议补充公司介绍、官网简介或白皮书。")

        summary = (
            f"已从 {len(materials)} 份材料中提取供应商基础信息，"
            f"识别到供应商“{vendor_name or '待人工确认'}”，"
            f"并自动补全采购表草稿。"
        )
        return (
            ProcurementAgentVendorDraft(
                vendor_name=vendor_name,
                source_platform=source_platform,
                source_url=source_url,
                profile_summary=profile_summary,
                procurement_notes=procurement_notes,
            ),
            summary,
            warnings,
        )

    def _extract_vendor_name(self, combined_text: str, materials: list[ProcurementMaterialText]) -> str:
        patterns = [
            r"(?:供应商名称|公司名称|企业名称|Vendor Name|Company Name)[:：]\s*([^\n\r。；;]{2,80})",
            r"(?:甲方|乙方)[:：]\s*([^\n\r。；;]{2,80})",
        ]
        for pattern in patterns:
            match = re.search(pattern, combined_text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip("：:，,。. ")

        first_meaningful_line = ""
        for item in materials:
            for line in item.text.splitlines():
                cleaned = line.strip(" #*-")
                if 3 <= len(cleaned) <= 80:
                    first_meaningful_line = cleaned
                    break
            if first_meaningful_line:
                break
        if first_meaningful_line and not re.search(r"(报价|whitepaper|隐私|policy|协议|合同)", first_meaningful_line, flags=re.IGNORECASE):
            return first_meaningful_line
        return ""

    def _extract_source_platform(self, source_url: str, materials: list[ProcurementMaterialText]) -> str:
        if source_url:
            host = urlparse(source_url).netloc.lower().replace("www.", "")
            if host:
                return host
        source_types = {item.source_type for item in materials}
        if "pdf" in source_types or "docx" in source_types:
            return "材料上传"
        return materials[0].source_type or "材料上传"

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
    ) -> str:
        note_lines = [
            f"{current_user.display_name or '采购人员'} 已上传 {len(materials)} 份供应商材料，建议先人工核对抽取结果再继续准入审查。",
            f"当前关联项目为“{project.title}”，采购类别为 {project.category or '未填写'}。",
            f"材料清单：{', '.join(item.name for item in materials[:4])}",
        ]
        lowered = combined_text.lower()
        if "报价" in combined_text or "price" in lowered or "fee" in lowered:
            note_lines.append("材料中包含报价或商务条件，建议结合采购比价结果一并复核。")
        if project.data_scope != "none" or "数据" in combined_text or "data" in lowered:
            note_lines.append("项目或材料涉及数据处理场景，后续需重点关注数据合规与安全要求。")
        if "合同" in combined_text or "agreement" in lowered or "msa" in lowered:
            note_lines.append("材料中已出现合同或协议相关内容，可在后续法务阶段继续复用。")
        return " ".join(note_lines)[:500]

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
    ) -> str:
        lines = [
            "请执行一轮采购供应商准入 Agent 审查任务。",
            "不要把这当成普通问答，而是要主动判断该供应商是否适合进入人工确认与后续法务阶段。",
            "请基于本地供应商准入制度、采购流程、审批矩阵和安全/合规资料完成以下动作：",
            "1. 判断该供应商是否建议继续绑定到当前项目。",
            "2. 总结主要风险点和阻塞项。",
            "3. 指出当前还缺哪些准入材料或公开信息。",
            "4. 给出下一步建议动作，只作为采购辅助结论，不替代人工最终决定。",
            "",
            "当前项目背景：",
            f"- 项目名称：{project.title}",
            f"- 发起部门：{project.department}",
            f"- 采购类别：{project.category}",
            f"- 预算：{project.budget_amount} {project.currency}",
            f"- 采购目的：{project.summary or '未填写'}",
            f"- 业务价值：{project.business_value or '未填写'}",
            f"- 计划上线时间：{project.target_go_live_date or '未填写'}",
            f"- 数据范围：{project.data_scope or 'none'}",
            "",
            "待审查供应商草稿：",
            f"- 供应商名称：{draft.vendor_name}",
            f"- 来源平台：{draft.source_platform}",
            f"- 来源链接：{draft.source_url or '未提供'}",
            f"- 供应商简介：{draft.profile_summary}",
            f"- 采购说明：{draft.procurement_notes}",
        ]
        if focus_points.strip():
            lines.extend(
                [
                    "",
                    "采购补充关注点：",
                    focus_points.strip(),
                ]
            )
        return "\n".join(lines)

    def _build_procurement_agent_assessment(
        self,
        project: ProcurementProject,
        draft: ProcurementAgentVendorDraft,
        review,
        focus_points: str,
    ) -> StructuredReviewRead:
        raw_risk_flags = self._extract_risk_flags(review)
        readable_risks = [self._risk_summary_from_flag(flag) for flag in raw_risk_flags]
        if draft.ai_recommendation == "recommend_proceed":
            conclusion = "建议采购可继续人工确认，并在确认无误后绑定到当前项目。"
        elif draft.ai_recommendation == "review_with_risks":
            conclusion = "存在风险但仍可继续人工复核，建议补齐关键材料后再决定是否绑定。"
        else:
            conclusion = "当前信息仍不足，建议继续收集公开资料和准入材料后再决定是否绑定。"

        completeness_ready = all(
            [
                draft.vendor_name,
                draft.source_platform,
                len(draft.profile_summary) >= 10,
                len(draft.procurement_notes) >= 10,
            ]
        )
        source_traceable = bool(draft.source_platform and (draft.source_url or "官网" in draft.source_platform))
        data_scope_sensitive = (project.data_scope or "none") != "none"

        check_items = [
            StructuredCheckItemRead(
                label="供应商基础信息完整度",
                status="pass" if completeness_ready else "warn",
                detail="已具备供应商名称、来源平台、简介和采购说明。" if completeness_ready else "供应商基本信息仍不完整，建议继续补齐。",
            ),
            StructuredCheckItemRead(
                label="来源可追溯性",
                status="pass" if source_traceable else "warn",
                detail="当前已具备可追溯的平台或来源链接。" if source_traceable else "建议补充官网、第三方平台链接或其他公开来源依据。",
            ),
            StructuredCheckItemRead(
                label="数据与合规关注",
                status="fail" if readable_risks else "warn" if data_scope_sensitive else "pass",
                detail="；".join(readable_risks[:3]) if readable_risks else "当前未发现明确的结构化风险标记，但涉及数据场景仍建议继续人工确认。" if data_scope_sensitive else "当前未发现明确的结构化风险标记。",
            ),
            StructuredCheckItemRead(
                label="Agent 准入建议",
                status="pass" if draft.ai_recommendation == "recommend_proceed" else "warn" if draft.ai_recommendation == "needs_follow_up" else "fail",
                detail=conclusion,
            ),
        ]

        open_questions: list[str] = []
        if not draft.source_url:
            open_questions.append("补充供应商官网或公开资料链接，便于后续人工复核。")
        if data_scope_sensitive:
            open_questions.append("确认供应商是否处理项目相关数据，并补充隐私政策、安全白皮书或数据处理说明。")
        if review.next_action != "answer":
            open_questions.append("当前证据覆盖不足，建议继续补充公开资料、准入材料或更明确的业务背景。")
        if focus_points.strip():
            open_questions.append(f"针对采购关注点“{focus_points.strip()}”继续做人工复核。")

        return StructuredReviewRead(
            review_kind="procurement_agent_review",
            conclusion=conclusion,
            recommendation=draft.ai_recommendation or "needs_follow_up",
            summary=review.answer,
            check_items=check_items,
            risk_flags=readable_risks,
            open_questions=open_questions[:4],
            evidence=self._build_evidence_items(review),
        )

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
            else "建议补充调查后再决定"
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
                    label="供应商基础资料",
                    status="pass" if vendor.profile_summary or vendor.source_url else "warn",
                    detail="已录入来源平台、简介或外部链接。" if vendor.profile_summary or vendor.source_url else "建议补充供应商公开信息与主页链接。",
                ),
                StructuredCheckItemRead(
                    label="准入建议",
                    status="pass" if vendor.ai_recommendation == "recommend_proceed" else "warn" if vendor.ai_recommendation == "needs_follow_up" else "fail",
                    detail=conclusion,
                ),
                StructuredCheckItemRead(
                    label="数据与合规风险",
                    status="fail" if risk_flags else "pass",
                    detail="；".join(risk_flags[:3]) if risk_flags else "当前未发现明确的结构化风险标记。",
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
        compare_summary = review.debug_summary.get("compare_summary", {}) if isinstance(review.debug_summary, dict) else {}
        missing_clauses = compare_summary.get("missing_clauses", {}) if isinstance(compare_summary, dict) else {}
        clause_details = []
        for doc_title, clauses in list(missing_clauses.items())[:2]:
            if clauses:
                clause_details.append(f"{doc_title} 缺少 {', '.join(clauses[:4])}")
        recommendation = self._derive_ai_recommendation(review.next_action, review.debug_summary)
        return StructuredReviewRead(
            review_kind="legal_contract_review",
            conclusion="建议退回采购重新筛选供应商" if risk_flags else "合同可进入人工法务决策",
            recommendation=recommendation,
            summary=review.answer,
            check_items=[
                StructuredCheckItemRead(
                    label="合同往返材料",
                    status="pass",
                    detail=f"已对 {vendor.vendor_name} 的我方模板与对方回传合同进行审查。",
                ),
                StructuredCheckItemRead(
                    label="红线条款差异",
                    status="fail" if clause_details else "pass",
                    detail="；".join(clause_details[:2]) if clause_details else "当前结构化对比未发现明确缺失条款。",
                ),
                StructuredCheckItemRead(
                    label="法务建议动作",
                    status="fail" if recommendation != "recommend_proceed" else "pass",
                    detail="存在风险，建议退回采购或人工复核。" if recommendation != "recommend_proceed" else "可进入人工法务通过/退回决策。",
                ),
            ],
            risk_flags=risk_flags,
            open_questions=self._legal_open_questions(review, clause_details),
            evidence=self._build_evidence_items(review),
        )

    def _extract_risk_flags(self, review) -> list[str]:
        debug_summary = review.debug_summary or {}
        risk_flags = list(debug_summary.get("risk_flags", []))
        compare_summary = debug_summary.get("compare_summary")
        if isinstance(compare_summary, dict):
            risk_flags.extend(compare_summary.get("risk_flags", []))
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
            questions.append("确认供应商对数据处理、存储与安全事件响应的说明。")
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
            return detail

        payload = detail.model_dump()
        payload["allowed_actions"] = self._allowed_actions(detail, current_user.role)
        payload["archives"] = []

        if current_user.role == "business":
            payload["vendors"] = []
            payload["artifacts"] = [artifact for artifact in payload["artifacts"] if artifact["stage"] in {"business_draft", "manager_review"}]
            payload["risks"] = []
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
                if artifact["artifact_type"] not in {"standard_contract_dispatch", "vendor_redline_contract"}
            ]
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
            latest_legal_review=latest_legal_review,
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
