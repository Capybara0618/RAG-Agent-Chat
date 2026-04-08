from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.entities import ProcurementProject, ProcurementStage, ProjectArtifact, ProjectRisk, ProjectStageRecord, ProjectTask
from app.repositories.project_repository import ProjectRepository
from app.schemas.chat import QueryRequest
from app.schemas.project import (
    ProjectAdvanceRequest,
    ProjectArtifactCreate,
    ProjectArtifactRead,
    ProjectArtifactUpdate,
    ProjectCreate,
    ProjectDecisionRead,
    ProjectDetailRead,
    ProjectReviewRequest,
    ProjectReviewResult,
    ProjectRiskRead,
    ProjectStageRecordRead,
    ProjectSummaryRead,
    ProjectTaskCreate,
    ProjectTaskRead,
    ProjectTaskUpdate,
    ProjectTimelineEvent,
)
from app.services.agent.service import KnowledgeOpsAgentService


@dataclass(frozen=True)
class StageBlueprint:
    stage: ProcurementStage
    owner_role: str
    required_tasks: list[tuple[str, str, str]]
    required_artifacts: list[tuple[str, str]]


class ProjectService:
    STAGE_ORDER = [
        ProcurementStage.draft.value,
        ProcurementStage.vendor_onboarding.value,
        ProcurementStage.security_review.value,
        ProcurementStage.legal_review.value,
        ProcurementStage.approval.value,
        ProcurementStage.signing.value,
        ProcurementStage.completed.value,
    ]

    STAGE_BLUEPRINTS = {
        ProcurementStage.draft.value: StageBlueprint(
            stage=ProcurementStage.draft,
            owner_role="business",
            required_tasks=[
                ("intake", "Confirm business need and timeline", "business"),
                ("intake", "Capture budget and supplier summary", "business"),
            ],
            required_artifacts=[],
        ),
        ProcurementStage.vendor_onboarding.value: StageBlueprint(
            stage=ProcurementStage.vendor_onboarding,
            owner_role="procurement",
            required_tasks=[
                ("checklist", "Validate vendor onboarding checklist", "procurement"),
                ("checklist", "Confirm vendor ownership and payment profile", "procurement"),
            ],
            required_artifacts=[
                ("business_license", "Business license"),
                ("banking", "Bank account verification"),
                ("tax", "Tax registration and invoice details"),
            ],
        ),
        ProcurementStage.security_review.value: StageBlueprint(
            stage=ProcurementStage.security_review,
            owner_role="security",
            required_tasks=[
                ("review", "Run security intake review", "security"),
                ("review", "Confirm data handling scope", "security"),
            ],
            required_artifacts=[
                ("security_questionnaire", "Security questionnaire"),
                ("architecture", "Architecture and data-flow overview"),
            ],
        ),
        ProcurementStage.legal_review.value: StageBlueprint(
            stage=ProcurementStage.legal_review,
            owner_role="legal",
            required_tasks=[
                ("review", "Review contract redlines and legal escalations", "legal"),
            ],
            required_artifacts=[
                ("standard_contract", "Standard contract template"),
                ("vendor_redline", "Vendor redline contract"),
            ],
        ),
        ProcurementStage.approval.value: StageBlueprint(
            stage=ProcurementStage.approval,
            owner_role="procurement",
            required_tasks=[
                ("approval", "Collect all required approvals", "procurement"),
            ],
            required_artifacts=[
                ("approval_matrix", "Approval matrix evidence"),
            ],
        ),
        ProcurementStage.signing.value: StageBlueprint(
            stage=ProcurementStage.signing,
            owner_role="procurement",
            required_tasks=[
                ("signature", "Prepare final signature package", "procurement"),
            ],
            required_artifacts=[
                ("final_contract", "Final approved contract"),
            ],
        ),
    }

    def __init__(self, *, repository: ProjectRepository, agent_service: KnowledgeOpsAgentService) -> None:
        self.repository = repository
        self.agent_service = agent_service

    def create_project(self, db: Session, payload: ProjectCreate) -> ProjectDetailRead:
        project = self.repository.create_project(
            db,
            title=payload.title,
            requester_name=payload.requester_name,
            department=payload.department,
            vendor_name=payload.vendor_name,
            category=payload.category,
            budget_amount=payload.budget_amount,
            currency=payload.currency,
            summary=payload.summary,
            data_scope=payload.data_scope,
        )
        self.repository.create_stage_record(
            db,
            project_id=project.id,
            stage=ProcurementStage.draft.value,
            status="active",
            owner_role=self.STAGE_BLUEPRINTS[ProcurementStage.draft.value].owner_role,
        )
        self._ensure_stage_defaults(db, project, ProcurementStage.draft.value)
        db.commit()
        return self.get_project_detail(db, project.id)

    def list_projects(self, db: Session) -> list[ProjectSummaryRead]:
        summaries: list[ProjectSummaryRead] = []
        for project in self.repository.list_projects(db):
            summaries.append(
                ProjectSummaryRead(
                    id=project.id,
                    title=project.title,
                    requester_name=project.requester_name,
                    department=project.department,
                    vendor_name=project.vendor_name,
                    category=project.category,
                    budget_amount=project.budget_amount,
                    currency=project.currency,
                    current_stage=project.current_stage,
                    risk_level=project.risk_level,
                    status=project.status,
                    current_owner_role=project.current_owner_role,
                    open_task_count=self.repository.count_open_tasks(db, project.id),
                    open_risk_count=self.repository.count_open_risks(db, project.id),
                    created_at=project.created_at,
                    updated_at=project.updated_at,
                )
            )
        return summaries

    def get_project_detail(self, db: Session, project_id: str) -> ProjectDetailRead:
        project = self._require_project(db, project_id)
        tasks = self.repository.list_tasks(db, project.id)
        artifacts = self.repository.list_artifacts(db, project.id)
        risks = self.repository.list_risks(db, project.id)
        decisions = self.repository.list_decisions(db, project.id)
        stages = self.repository.list_stage_records(db, project.id)
        blockers = self._collect_blockers(tasks, artifacts, project.current_stage)
        return self._serialize_detail(project, tasks, artifacts, risks, decisions, stages, blockers)

    def advance_project(self, db: Session, project_id: str, payload: ProjectAdvanceRequest) -> ProjectDetailRead:
        project = self._require_project(db, project_id)
        target_stage = payload.target_stage or self._next_stage(project.current_stage)
        if target_stage is None:
            raise ValueError("Project is already in a terminal stage.")
        blockers = self._collect_blockers(
            self.repository.list_tasks(db, project.id),
            self.repository.list_artifacts(db, project.id),
            project.current_stage,
        )
        if blockers:
            raise ValueError("Current stage still has unresolved blockers.")

        active_record = self.repository.get_active_stage_record(db, project.id)
        if active_record is not None:
            active_record.status = "completed"
            active_record.ended_at = datetime.utcnow()

        owner_role = self.STAGE_BLUEPRINTS.get(target_stage, StageBlueprint(ProcurementStage.completed, "procurement", [], [])).owner_role
        project.current_stage = target_stage
        project.current_owner_role = owner_role
        project.status = "completed" if target_stage == ProcurementStage.completed.value else "active"
        self.repository.create_stage_record(
            db,
            project_id=project.id,
            stage=target_stage,
            status="active",
            owner_role=owner_role,
        )
        self._ensure_stage_defaults(db, project, target_stage)
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
        db.commit()
        return ProjectTaskRead.model_validate(task)

    def update_task(self, db: Session, project_id: str, task_id: str, payload: ProjectTaskUpdate) -> ProjectTaskRead:
        self._require_project(db, project_id)
        task = self.repository.get_task(db, task_id)
        if task is None or task.project_id != project_id:
            raise ValueError("Project task not found.")
        task.status = payload.status
        db.commit()
        db.refresh(task)
        return ProjectTaskRead.model_validate(task)

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
            status=payload.status,
            notes=payload.notes,
        )
        db.commit()
        return ProjectArtifactRead.model_validate(artifact)

    def update_artifact(self, db: Session, project_id: str, artifact_id: str, payload: ProjectArtifactUpdate) -> ProjectArtifactRead:
        self._require_project(db, project_id)
        artifact = self.repository.get_artifact(db, artifact_id)
        if artifact is None or artifact.project_id != project_id:
            raise ValueError("Project artifact not found.")
        artifact.status = payload.status
        if payload.document_id:
            artifact.document_id = payload.document_id
        artifact.notes = payload.notes
        db.commit()
        db.refresh(artifact)
        return ProjectArtifactRead.model_validate(artifact)

    def review_project(self, db: Session, project_id: str, payload: ProjectReviewRequest) -> ProjectReviewResult:
        project = self._require_project(db, project_id)
        review = self.agent_service.query(
            db,
            QueryRequest(
                query=payload.query,
                session_id=project.chat_session_id or None,
                user_role=payload.user_role,
                top_k=payload.top_k,
            ),
        )
        project.chat_session_id = review.session_id
        self.repository.create_decision(
            db,
            project_id=project.id,
            stage=project.current_stage,
            decision_type="ai_review",
            decision_by="system",
            decision_summary=review.answer,
            trace_id=review.trace_id,
        )
        self.repository.clear_stage_risks(db, project.id, project.current_stage)
        risks = self._materialize_risks(db, project, review)
        project.risk_level = self._derive_risk_level(risks, review.next_action)
        active_record = self.repository.get_active_stage_record(db, project.id)
        blockers = self._collect_blockers(
            self.repository.list_tasks(db, project.id),
            self.repository.list_artifacts(db, project.id),
            project.current_stage,
        )
        if review.next_action != "answer":
            blockers.insert(0, f"AI review returned '{review.next_action}' and requires follow-up.")
        if active_record is not None:
            active_record.blocking_reason = " | ".join(blockers[:3]) if blockers else ""
        db.commit()
        detail = self.get_project_detail(db, project.id)
        return ProjectReviewResult(project=detail, review=review, risks=[ProjectRiskRead.model_validate(risk) for risk in risks])

    def get_timeline(self, db: Session, project_id: str) -> list[ProjectTimelineEvent]:
        project = self._require_project(db, project_id)
        events: list[ProjectTimelineEvent] = []
        for stage in self.repository.list_stage_records(db, project.id):
            events.append(
                ProjectTimelineEvent(
                    kind="stage",
                    stage=stage.stage,
                    title=f"Entered {stage.stage}",
                    summary=stage.blocking_reason or f"Owner: {stage.owner_role}",
                    created_at=stage.started_at,
                )
            )
        for decision in self.repository.list_decisions(db, project.id):
            events.append(
                ProjectTimelineEvent(
                    kind="decision",
                    stage=decision.stage,
                    title="AI review",
                    summary=decision.decision_summary[:220],
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

    def _next_stage(self, stage: str) -> str | None:
        if stage not in self.STAGE_ORDER:
            return None
        index = self.STAGE_ORDER.index(stage)
        if index >= len(self.STAGE_ORDER) - 1:
            return None
        return self.STAGE_ORDER[index + 1]

    def _ensure_stage_defaults(self, db: Session, project: ProcurementProject, stage: str) -> None:
        blueprint = self.STAGE_BLUEPRINTS.get(stage)
        if blueprint is None:
            return
        existing_tasks = {(task.stage, task.title) for task in self.repository.list_tasks(db, project.id)}
        existing_artifacts = {(artifact.stage, artifact.title) for artifact in self.repository.list_artifacts(db, project.id)}
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
        for artifact_type, title in blueprint.required_artifacts:
            if (stage, title) not in existing_artifacts:
                self.repository.create_artifact(
                    db,
                    project_id=project.id,
                    stage=stage,
                    artifact_type=artifact_type,
                    title=title,
                    required=True,
                    document_id="",
                    status="missing",
                    notes="",
                )

    def _collect_blockers(self, tasks: list[ProjectTask], artifacts: list[ProjectArtifact], current_stage: str) -> list[str]:
        blockers: list[str] = []
        for task in tasks:
            if task.stage == current_stage and task.required and task.status != "done":
                blockers.append(f"Task pending: {task.title}")
        for artifact in artifacts:
            if artifact.stage == current_stage and artifact.required and artifact.status not in {"provided", "approved"}:
                blockers.append(f"Artifact missing: {artifact.title}")
        return blockers

    def _materialize_risks(self, db: Session, project: ProcurementProject, review) -> list[ProjectRisk]:
        risks: list[ProjectRisk] = []
        debug_summary = review.debug_summary or {}
        risk_flags = list(debug_summary.get("risk_flags", []))
        compare_summary = debug_summary.get("compare_summary")
        if isinstance(compare_summary, dict):
            for flag in compare_summary.get("risk_flags", []):
                risk_flags.append(flag)
        if not risk_flags and review.next_action != "answer":
            risk_flags.append("manual_follow_up_required")
        for flag in risk_flags:
            summary = self._risk_summary_from_flag(flag)
            severity = self._risk_severity_from_flag(flag)
            risks.append(
                self.repository.create_risk(
                    db,
                    project_id=project.id,
                    stage=project.current_stage,
                    risk_type=str(flag),
                    severity=severity,
                    summary=summary,
                    status="open",
                    trace_id=review.trace_id,
                )
            )
        return risks

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

    def _serialize_detail(
        self,
        project: ProcurementProject,
        tasks: list[ProjectTask],
        artifacts: list[ProjectArtifact],
        risks: list[ProjectRisk],
        decisions: list,
        stages: list[ProjectStageRecord],
        blockers: list[str],
    ) -> ProjectDetailRead:
        return ProjectDetailRead(
            id=project.id,
            title=project.title,
            requester_name=project.requester_name,
            department=project.department,
            vendor_name=project.vendor_name,
            category=project.category,
            budget_amount=project.budget_amount,
            currency=project.currency,
            summary=project.summary,
            data_scope=project.data_scope,
            current_stage=project.current_stage,
            risk_level=project.risk_level,
            status=project.status,
            current_owner_role=project.current_owner_role,
            chat_session_id=project.chat_session_id,
            blocker_summary=blockers,
            tasks=[ProjectTaskRead.model_validate(task) for task in tasks],
            artifacts=[ProjectArtifactRead.model_validate(artifact) for artifact in artifacts],
            risks=[ProjectRiskRead.model_validate(risk) for risk in risks],
            decisions=[ProjectDecisionRead.model_validate(decision) for decision in decisions],
            stages=[ProjectStageRecordRead.model_validate(stage) for stage in stages],
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
