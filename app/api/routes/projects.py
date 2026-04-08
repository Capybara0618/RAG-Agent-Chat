from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_project_service
from app.schemas.project import (
    ProjectAdvanceRequest,
    ProjectArtifactCreate,
    ProjectArtifactRead,
    ProjectArtifactUpdate,
    ProjectCreate,
    ProjectDetailRead,
    ProjectReviewRequest,
    ProjectReviewResult,
    ProjectRiskRead,
    ProjectSummaryRead,
    ProjectTaskCreate,
    ProjectTaskRead,
    ProjectTaskUpdate,
    ProjectTimelineEvent,
)
from app.services.project_service import ProjectService


router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectSummaryRead])
def list_projects(
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
) -> list[ProjectSummaryRead]:
    return project_service.list_projects(db)


@router.post("", response_model=ProjectDetailRead)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectDetailRead:
    return project_service.create_project(db, payload)


@router.get("/{project_id}", response_model=ProjectDetailRead)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectDetailRead:
    try:
        return project_service.get_project_detail(db, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/advance", response_model=ProjectDetailRead)
def advance_project(
    project_id: str,
    payload: ProjectAdvanceRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectDetailRead:
    try:
        return project_service.advance_project(db, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/tasks", response_model=ProjectTaskRead)
def create_task(
    project_id: str,
    payload: ProjectTaskCreate,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectTaskRead:
    try:
        return project_service.create_task(db, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{project_id}/tasks/{task_id}", response_model=ProjectTaskRead)
def update_task(
    project_id: str,
    task_id: str,
    payload: ProjectTaskUpdate,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectTaskRead:
    try:
        return project_service.update_task(db, project_id, task_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/artifacts", response_model=ProjectArtifactRead)
def create_artifact(
    project_id: str,
    payload: ProjectArtifactCreate,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectArtifactRead:
    try:
        return project_service.create_artifact(db, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{project_id}/artifacts/{artifact_id}", response_model=ProjectArtifactRead)
def update_artifact(
    project_id: str,
    artifact_id: str,
    payload: ProjectArtifactUpdate,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectArtifactRead:
    try:
        return project_service.update_artifact(db, project_id, artifact_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/review/query", response_model=ProjectReviewResult)
def review_project(
    project_id: str,
    payload: ProjectReviewRequest,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectReviewResult:
    try:
        return project_service.review_project(db, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{project_id}/timeline", response_model=list[ProjectTimelineEvent])
def get_timeline(
    project_id: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
) -> list[ProjectTimelineEvent]:
    try:
        return project_service.get_timeline(db, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{project_id}/risks", response_model=list[ProjectRiskRead])
def list_risks(
    project_id: str,
    db: Session = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
) -> list[ProjectRiskRead]:
    try:
        return project_service.list_risks(db, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
