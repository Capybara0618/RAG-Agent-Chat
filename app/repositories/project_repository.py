from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    ProcurementProject,
    ProjectArtifact,
    ProjectDecision,
    ProjectRisk,
    ProjectStageRecord,
    ProjectTask,
)


class ProjectRepository:
    def create_project(
        self,
        db: Session,
        *,
        title: str,
        requester_name: str,
        department: str,
        vendor_name: str,
        category: str,
        budget_amount: float,
        currency: str,
        summary: str,
        data_scope: str,
    ) -> ProcurementProject:
        project = ProcurementProject(
            title=title,
            requester_name=requester_name,
            department=department,
            vendor_name=vendor_name,
            category=category,
            budget_amount=budget_amount,
            currency=currency,
            summary=summary,
            data_scope=data_scope,
        )
        db.add(project)
        db.flush()
        return project

    def get_project(self, db: Session, project_id: str) -> ProcurementProject | None:
        return db.get(ProcurementProject, project_id)

    def list_projects(self, db: Session) -> list[ProcurementProject]:
        statement = select(ProcurementProject).order_by(ProcurementProject.updated_at.desc())
        return list(db.scalars(statement))

    def create_stage_record(
        self,
        db: Session,
        *,
        project_id: str,
        stage: str,
        status: str,
        owner_role: str,
        blocking_reason: str = "",
    ) -> ProjectStageRecord:
        record = ProjectStageRecord(
            project_id=project_id,
            stage=stage,
            status=status,
            owner_role=owner_role,
            blocking_reason=blocking_reason,
        )
        db.add(record)
        db.flush()
        return record

    def list_stage_records(self, db: Session, project_id: str) -> list[ProjectStageRecord]:
        statement = select(ProjectStageRecord).where(ProjectStageRecord.project_id == project_id).order_by(ProjectStageRecord.started_at.asc())
        return list(db.scalars(statement))

    def get_active_stage_record(self, db: Session, project_id: str) -> ProjectStageRecord | None:
        statement = (
            select(ProjectStageRecord)
            .where(ProjectStageRecord.project_id == project_id, ProjectStageRecord.status == "active")
            .order_by(ProjectStageRecord.started_at.desc())
        )
        return db.scalar(statement)

    def create_task(
        self,
        db: Session,
        *,
        project_id: str,
        stage: str,
        task_type: str,
        title: str,
        details: str,
        assignee_role: str,
        required: bool,
    ) -> ProjectTask:
        task = ProjectTask(
            project_id=project_id,
            stage=stage,
            task_type=task_type,
            title=title,
            details=details,
            assignee_role=assignee_role,
            required=required,
        )
        db.add(task)
        db.flush()
        return task

    def get_task(self, db: Session, task_id: str) -> ProjectTask | None:
        return db.get(ProjectTask, task_id)

    def list_tasks(self, db: Session, project_id: str) -> list[ProjectTask]:
        statement = select(ProjectTask).where(ProjectTask.project_id == project_id).order_by(ProjectTask.created_at.asc())
        return list(db.scalars(statement))

    def create_artifact(
        self,
        db: Session,
        *,
        project_id: str,
        stage: str,
        artifact_type: str,
        title: str,
        required: bool,
        document_id: str,
        status: str,
        notes: str,
    ) -> ProjectArtifact:
        artifact = ProjectArtifact(
            project_id=project_id,
            stage=stage,
            artifact_type=artifact_type,
            title=title,
            required=required,
            document_id=document_id,
            status=status,
            notes=notes,
        )
        db.add(artifact)
        db.flush()
        return artifact

    def get_artifact(self, db: Session, artifact_id: str) -> ProjectArtifact | None:
        return db.get(ProjectArtifact, artifact_id)

    def list_artifacts(self, db: Session, project_id: str) -> list[ProjectArtifact]:
        statement = select(ProjectArtifact).where(ProjectArtifact.project_id == project_id).order_by(ProjectArtifact.created_at.asc())
        return list(db.scalars(statement))

    def create_decision(
        self,
        db: Session,
        *,
        project_id: str,
        stage: str,
        decision_type: str,
        decision_by: str,
        decision_summary: str,
        trace_id: str,
    ) -> ProjectDecision:
        decision = ProjectDecision(
            project_id=project_id,
            stage=stage,
            decision_type=decision_type,
            decision_by=decision_by,
            decision_summary=decision_summary,
            trace_id=trace_id,
        )
        db.add(decision)
        db.flush()
        return decision

    def list_decisions(self, db: Session, project_id: str) -> list[ProjectDecision]:
        statement = select(ProjectDecision).where(ProjectDecision.project_id == project_id).order_by(ProjectDecision.created_at.desc())
        return list(db.scalars(statement))

    def create_risk(
        self,
        db: Session,
        *,
        project_id: str,
        stage: str,
        risk_type: str,
        severity: str,
        summary: str,
        status: str,
        trace_id: str,
    ) -> ProjectRisk:
        risk = ProjectRisk(
            project_id=project_id,
            stage=stage,
            risk_type=risk_type,
            severity=severity,
            summary=summary,
            status=status,
            trace_id=trace_id,
        )
        db.add(risk)
        db.flush()
        return risk

    def list_risks(self, db: Session, project_id: str) -> list[ProjectRisk]:
        statement = select(ProjectRisk).where(ProjectRisk.project_id == project_id).order_by(ProjectRisk.created_at.desc())
        return list(db.scalars(statement))

    def clear_stage_risks(self, db: Session, project_id: str, stage: str) -> None:
        statement = select(ProjectRisk).where(ProjectRisk.project_id == project_id, ProjectRisk.stage == stage)
        for risk in db.scalars(statement):
            db.delete(risk)
        db.flush()

    def count_open_tasks(self, db: Session, project_id: str) -> int:
        statement = select(func.count(ProjectTask.id)).where(ProjectTask.project_id == project_id, ProjectTask.status != "done")
        return int(db.scalar(statement) or 0)

    def count_open_risks(self, db: Session, project_id: str) -> int:
        statement = select(func.count(ProjectRisk.id)).where(ProjectRisk.project_id == project_id, ProjectRisk.status == "open")
        return int(db.scalar(statement) or 0)
