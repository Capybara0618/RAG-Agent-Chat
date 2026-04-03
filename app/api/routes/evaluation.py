from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_evaluation_service
from app.schemas.evaluation import EvalRunRead, EvalRunRequest
from app.services.evaluation.service import EvaluationService


router = APIRouter(prefix="/eval", tags=["evaluation"])


@router.post("/run", response_model=EvalRunRead)
def run_evaluation(
    payload: EvalRunRequest,
    db: Session = Depends(get_db),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> EvalRunRead:
    return evaluation_service.run(db, payload.case_ids)


@router.get("/runs/{run_id}", response_model=EvalRunRead)
def get_evaluation_run(
    run_id: str,
    db: Session = Depends(get_db),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> EvalRunRead:
    run = evaluation_service.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    return run