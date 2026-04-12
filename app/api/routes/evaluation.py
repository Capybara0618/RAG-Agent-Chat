from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_evaluation_service, require_roles
from app.schemas.auth import UserProfileRead
from app.schemas.evaluation import EvalCaseCreate, EvalCaseRead, EvalRunRead, EvalRunRequest
from app.services.evaluation.service import EvaluationService


router = APIRouter(prefix="/eval", tags=["evaluation"])


@router.get("/cases", response_model=list[EvalCaseRead])
def list_eval_cases(
    task_types: list[str] = Query(default=[]),
    required_roles: list[str] = Query(default=[]),
    knowledge_domains: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
    _: UserProfileRead = Depends(require_roles("admin")),
) -> list[EvalCaseRead]:
    return evaluation_service.list_cases(
        db,
        task_types=task_types or None,
        required_roles=required_roles or None,
        knowledge_domains=knowledge_domains or None,
    )


@router.post("/cases", response_model=EvalCaseRead)
def create_eval_case(
    payload: EvalCaseCreate,
    db: Session = Depends(get_db),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
    _: UserProfileRead = Depends(require_roles("admin")),
) -> EvalCaseRead:
    return evaluation_service.create_case(db, payload)


@router.post("/run", response_model=EvalRunRead)
def run_evaluation(
    payload: EvalRunRequest,
    db: Session = Depends(get_db),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
    _: UserProfileRead = Depends(require_roles("admin")),
) -> EvalRunRead:
    return evaluation_service.run(db, payload)


@router.get("/runs/{run_id}", response_model=EvalRunRead)
def get_evaluation_run(
    run_id: str,
    db: Session = Depends(get_db),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
    _: UserProfileRead = Depends(require_roles("admin")),
) -> EvalRunRead:
    run = evaluation_service.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    return run
