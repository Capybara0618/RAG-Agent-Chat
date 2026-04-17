from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db, get_ingestion_service, get_project_service
from app.schemas.auth import UserProfileRead
from app.schemas.project import (
    ProcurementAgentExtractResult,
    ProcurementAgentRunResult,
    ProcurementAgentReviewRequest,
    ProcurementAgentReviewResult,
    ProjectArtifactCreate,
    ProjectArtifactPreviewRead,
    ProjectArtifactRead,
    ProjectArtifactUpdate,
    ProjectCancelRequest,
    ProjectCreate,
    ProjectDetailRead,
    ProjectFinalApproveRequest,
    ProjectFinalReturnRequest,
    ProjectLegalDecisionRequest,
    ProjectLegalReviewRequest,
    ProjectLegalReviewResult,
    ProjectManagerDecisionRequest,
    ProjectRiskRead,
    ProjectSignRequest,
    ProjectSubmitRequest,
    ProjectSummaryRead,
    ProjectTaskCreate,
    ProjectTaskRead,
    ProjectTaskUpdate,
    ProjectTimelineEvent,
    ProjectUpdate,
    ProjectWithdrawRequest,
    VendorCandidateCreate,
    VendorCandidateRead,
    VendorReviewRequest,
    VendorReviewResult,
    VendorSelectRequest,
)
from app.services.ingestion.service import IngestionService
from app.services.project_service import ProjectService


router = APIRouter(prefix="/projects", tags=["projects"])
LEGAL_CONTRACT_UPLOAD_SUFFIXES = {".md", ".markdown", ".docx"}


@router.get("", response_model=list[ProjectSummaryRead])
def list_projects(
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> list[ProjectSummaryRead]:
    return project_service.list_projects_for_user(db, current_user)


@router.post("", response_model=ProjectDetailRead)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectDetailRead:
    try:
        project_service.assert_can_create_project(current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    normalized_payload = payload.model_copy(
        update={
            "department": current_user.department if current_user.role == "business" else payload.department,
            "requester_name": payload.requester_name or current_user.display_name,
        }
    )
    detail = project_service.create_project(db, normalized_payload, created_by_user_id=current_user.id)
    return project_service.get_project_detail_for_user(db, detail.id, current_user)


@router.post("/demo", response_model=ProjectDetailRead)
def create_demo_project(
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectDetailRead:
    try:
        project_service.assert_can_create_demo_project(current_user)
        detail = project_service.create_demo_project(db, created_by_user_id=current_user.id)
        return project_service.get_project_detail_for_user(db, detail.id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/{project_id}", response_model=ProjectDetailRead)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectDetailRead:
    try:
        return project_service.get_project_detail_for_user(db, project_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{project_id}", response_model=ProjectDetailRead)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectDetailRead:
    try:
        project_service.assert_can_manage_stage(db, project_id, current_user, "update")
        normalized_payload = payload.model_copy(
            update={"department": current_user.department if current_user.role == "business" else payload.department}
        )
        detail = project_service.update_project(db, project_id, normalized_payload)
        return project_service.get_project_detail_for_user(db, detail.id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/submit", response_model=ProjectDetailRead)
def submit_project(
    project_id: str,
    payload: ProjectSubmitRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectDetailRead:
    try:
        project_service.assert_can_manage_stage(db, project_id, current_user, "submit")
        detail = project_service.submit_project(
            db,
            project_id,
            payload.model_copy(update={"actor_role": current_user.role}),
        )
        return project_service.get_project_detail_for_user(db, detail.id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/withdraw", response_model=ProjectDetailRead)
def withdraw_project(
    project_id: str,
    payload: ProjectWithdrawRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectDetailRead:
    try:
        project_service.assert_can_manage_stage(db, project_id, current_user, "withdraw")
        detail = project_service.withdraw_project(
            db,
            project_id,
            payload.model_copy(update={"actor_role": current_user.role}),
        )
        return project_service.get_project_detail_for_user(db, detail.id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/manager-decision", response_model=ProjectDetailRead)
def manager_decision(
    project_id: str,
    payload: ProjectManagerDecisionRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectDetailRead:
    try:
        project_service.assert_can_manage_stage(
            db,
            project_id,
            current_user,
            "manager_approve" if payload.decision == "approve" else "manager_return",
        )
        detail = project_service.manager_decision(
            db,
            project_id,
            payload.model_copy(update={"actor_role": current_user.role}),
        )
        return project_service.get_project_detail_for_user(db, detail.id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/tasks", response_model=ProjectTaskRead)
def create_task(
    project_id: str,
    payload: ProjectTaskCreate,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectTaskRead:
    try:
        project_service.assert_can_work_on_current_stage(db, project_id, current_user)
        return project_service.create_task(db, project_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{project_id}/tasks/{task_id}", response_model=ProjectTaskRead)
def update_task(
    project_id: str,
    task_id: str,
    payload: ProjectTaskUpdate,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectTaskRead:
    try:
        project_service.assert_can_work_on_current_stage(db, project_id, current_user)
        return project_service.update_task(db, project_id, task_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/artifacts/{artifact_id}/upload", response_model=ProjectArtifactRead)
async def upload_project_artifact(
    project_id: str,
    artifact_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectArtifactRead:
    try:
        project_service.assert_can_work_on_current_stage(db, project_id, current_user)
        project_service.get_project_detail_for_user(db, project_id, current_user)
        artifact = project_service.repository.get_artifact(db, artifact_id)
        if artifact is None or artifact.project_id != project_id:
            raise ValueError("Project artifact not found.")

        original_name = Path(file.filename or "contract.bin").name
        suffix = Path(original_name).suffix.lower()
        if suffix not in LEGAL_CONTRACT_UPLOAD_SUFFIXES:
            raise ValueError("Legal contract upload currently supports only .md and .docx files.")
        file_bytes = await file.read()
        if not file_bytes:
            raise ValueError("Uploaded file is empty.")

        stored_name = f"{project_id}_{artifact_id}_{original_name}"
        stored_path = ingestion_service.persist_upload(stored_name, file_bytes)
        source = ingestion_service.submit_ingestion(
            db,
            name=f"[{project_id[:8]}] {artifact.title}{suffix}",
            data=file_bytes,
            allowed_roles="manager,procurement,legal,admin",
            tags=f"project_artifact,{project_id},{artifact.artifact_type},legal_contract",
            source_path=stored_path,
        )
        db.commit()
        if not source.duplicate:
            ingestion_service.run_indexing_task(source.task_id)

        artifact_note = (
            f"已上传文件：{original_name}。请以此版本作为法务对比基准。"
            if artifact.artifact_type == "our_procurement_contract"
            else f"已上传文件：{original_name}。系统将把该版本与我方采购合同逐条对比。"
            if artifact.artifact_type == "counterparty_redline_contract"
            else f"已上传文件：{original_name}。"
        )
        return project_service.update_artifact(
            db,
            project_id,
            artifact_id,
            ProjectArtifactUpdate(
                status="provided",
                document_id=source.source.id,
                notes=artifact_note,
            ),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/artifacts/{artifact_id}/preview", response_model=ProjectArtifactPreviewRead)
def get_project_artifact_preview(
    project_id: str,
    artifact_id: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectArtifactPreviewRead:
    try:
        project_service.get_project_detail_for_user(db, project_id, current_user)
        return project_service.get_artifact_preview(db, project_id, artifact_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/vendors", response_model=VendorCandidateRead)
def create_vendor(
    project_id: str,
    payload: VendorCandidateCreate,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> VendorCandidateRead:
    try:
        project_service.assert_can_manage_stage(db, project_id, current_user, "add_vendor")
        return project_service.create_vendor_candidate(db, project_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/procurement-agent-review", response_model=ProcurementAgentReviewResult)
def procurement_agent_review(
    project_id: str,
    payload: ProcurementAgentReviewRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProcurementAgentReviewResult:
    try:
        project_service.assert_can_manage_stage(db, project_id, current_user, "review_vendor")
        return project_service.procurement_agent_review(
            db,
            project_id,
            payload.model_copy(update={"user_role": current_user.role}),
            current_user=current_user,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/procurement-agent-extract", response_model=ProcurementAgentExtractResult)
async def procurement_agent_extract(
    project_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProcurementAgentExtractResult:
    try:
        project_service.assert_can_manage_stage(db, project_id, current_user, "add_vendor")
        uploaded_files = []
        for item in files:
            if item.filename:
                uploaded_files.append((item.filename, await item.read()))
        return project_service.extract_procurement_vendor_materials(
            db,
            project_id,
            uploaded_files=uploaded_files,
            current_user=current_user,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/procurement-agent-run", response_model=ProcurementAgentRunResult)
async def procurement_agent_run(
    project_id: str,
    files: list[UploadFile] = File(...),
    focus_points: str = Form(""),
    top_k: int = Form(6),
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProcurementAgentRunResult:
    try:
        project_service.assert_can_manage_stage(db, project_id, current_user, "review_vendor")
        uploaded_files = []
        for item in files:
            if item.filename:
                uploaded_files.append((item.filename, await item.read()))
        return project_service.procurement_agent_run_from_materials(
            db,
            project_id,
            uploaded_files=uploaded_files,
            focus_points=focus_points,
            top_k=top_k,
            current_user=current_user,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/vendors/{vendor_id}/review", response_model=VendorReviewResult)
def review_vendor(
    project_id: str,
    vendor_id: str,
    payload: VendorReviewRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> VendorReviewResult:
    try:
        project_service.assert_can_manage_stage(db, project_id, current_user, "review_vendor")
        return project_service.review_vendor(
            db,
            project_id,
            vendor_id,
            payload.model_copy(update={"user_role": current_user.role}),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/vendors/{vendor_id}/select", response_model=ProjectDetailRead)
def select_vendor(
    project_id: str,
    vendor_id: str,
    payload: VendorSelectRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectDetailRead:
    try:
        project_service.assert_can_manage_stage(db, project_id, current_user, "select_vendor")
        detail = project_service.select_vendor(
            db,
            project_id,
            vendor_id,
            payload.model_copy(update={"actor_role": current_user.role}),
        )
        return project_service.get_project_detail_for_user(db, detail.id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/artifacts", response_model=ProjectArtifactRead)
def create_artifact(
    project_id: str,
    payload: ProjectArtifactCreate,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectArtifactRead:
    try:
        project_service.assert_can_work_on_current_stage(db, project_id, current_user)
        return project_service.create_artifact(db, project_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{project_id}/artifacts/{artifact_id}", response_model=ProjectArtifactRead)
def update_artifact(
    project_id: str,
    artifact_id: str,
    payload: ProjectArtifactUpdate,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectArtifactRead:
    try:
        project_service.assert_can_work_on_current_stage(db, project_id, current_user)
        return project_service.update_artifact(db, project_id, artifact_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/legal/review", response_model=ProjectLegalReviewResult)
def legal_review(
    project_id: str,
    payload: ProjectLegalReviewRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectLegalReviewResult:
    try:
        project_service.assert_can_manage_stage(db, project_id, current_user, "review_legal")
        return project_service.legal_review(
            db,
            project_id,
            payload.model_copy(update={"user_role": current_user.role}),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/legal-decision", response_model=ProjectDetailRead)
def legal_decision(
    project_id: str,
    payload: ProjectLegalDecisionRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectDetailRead:
    try:
        project_service.assert_can_manage_stage(
            db,
            project_id,
            current_user,
            "legal_approve" if payload.decision == "approve" else "return_to_procurement",
        )
        detail = project_service.legal_decision(
            db,
            project_id,
            payload.model_copy(update={"actor_role": current_user.role}),
        )
        return project_service.get_project_detail_for_user(db, detail.id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/return-to-procurement", response_model=ProjectDetailRead)
def return_to_procurement(
    project_id: str,
    payload: ProjectWithdrawRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectDetailRead:
    try:
        project_service.assert_can_manage_stage(db, project_id, current_user, "return_to_procurement")
        detail = project_service.legal_decision(
            db,
            project_id,
            ProjectLegalDecisionRequest(decision="return", actor_role=current_user.role, reason=payload.reason),
        )
        return project_service.get_project_detail_for_user(db, detail.id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/final-approve", response_model=ProjectDetailRead)
def final_approve(
    project_id: str,
    payload: ProjectFinalApproveRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectDetailRead:
    try:
        project_service.assert_can_manage_stage(db, project_id, current_user, "final_approve")
        detail = project_service.final_approve(
            db,
            project_id,
            payload.model_copy(update={"actor_role": current_user.role}),
        )
        return project_service.get_project_detail_for_user(db, detail.id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/final-return", response_model=ProjectDetailRead)
def final_return(
    project_id: str,
    payload: ProjectFinalReturnRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectDetailRead:
    try:
        project_service.assert_can_manage_stage(
            db,
            project_id,
            current_user,
            "final_return_legal" if payload.target_stage == "legal_review" else "final_return_procurement",
        )
        detail = project_service.final_return(
            db,
            project_id,
            payload.model_copy(update={"actor_role": current_user.role}),
        )
        return project_service.get_project_detail_for_user(db, detail.id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/cancel", response_model=ProjectDetailRead)
def cancel_project(
    project_id: str,
    payload: ProjectCancelRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectDetailRead:
    try:
        project_service.assert_can_manage_stage(db, project_id, current_user, "cancel")
        detail = project_service.cancel_project(
            db,
            project_id,
            payload.model_copy(update={"actor_role": current_user.role}),
        )
        return project_service.get_project_detail_for_user(db, detail.id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/sign", response_model=ProjectDetailRead)
def sign_project(
    project_id: str,
    payload: ProjectSignRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> ProjectDetailRead:
    try:
        project_service.assert_can_manage_stage(db, project_id, current_user, "sign")
        detail = project_service.sign_project(
            db,
            project_id,
            payload.model_copy(update={"actor_role": current_user.role}),
        )
        return project_service.get_project_detail_for_user(db, detail.id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/timeline", response_model=list[ProjectTimelineEvent])
def get_timeline(
    project_id: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> list[ProjectTimelineEvent]:
    try:
        project_service.assert_can_view_project(db, project_id, current_user)
        return project_service.get_timeline(db, project_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{project_id}/risks", response_model=list[ProjectRiskRead])
def list_risks(
    project_id: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> list[ProjectRiskRead]:
    try:
        project_service.assert_can_view_project(db, project_id, current_user)
        return project_service.list_risks(db, project_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
