from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import EvalCase, EvalResult, EvalRun


class EvaluationRepository:
    def list_cases(self, db: Session) -> list[EvalCase]:
        statement = select(EvalCase).order_by(EvalCase.created_at.asc())
        return list(db.scalars(statement))

    def get_cases(self, db: Session, case_ids: list[str]) -> list[EvalCase]:
        if not case_ids:
            return self.list_cases(db)
        statement = select(EvalCase).where(EvalCase.id.in_(case_ids)).order_by(EvalCase.created_at.asc())
        return list(db.scalars(statement))

    def create_case(
        self,
        db: Session,
        *,
        question: str,
        expected_answer: str,
        expected_document_title: str,
        task_type: str,
        required_role: str,
    ) -> EvalCase:
        case = EvalCase(
            question=question,
            expected_answer=expected_answer,
            expected_document_title=expected_document_title,
            task_type=task_type,
            required_role=required_role,
        )
        db.add(case)
        db.flush()
        return case

    def create_run(self, db: Session) -> EvalRun:
        run = EvalRun()
        db.add(run)
        db.flush()
        return run

    def add_result(
        self,
        db: Session,
        *,
        run_id: str,
        case_id: str,
        answer: str,
        score_recall: float,
        score_citation: float,
        score_safety: float,
        passed: bool,
        notes: str,
    ) -> None:
        result = EvalResult(
            run_id=run_id,
            case_id=case_id,
            answer=answer,
            score_recall=score_recall,
            score_citation=score_citation,
            score_safety=score_safety,
            passed=passed,
            notes=notes,
        )
        db.add(result)
        db.flush()

    def finalize_run(
        self,
        db: Session,
        *,
        run_id: str,
        metrics: dict[str, float],
        failure_examples: list[dict[str, str | float]],
    ) -> EvalRun:
        run = db.get(EvalRun, run_id)
        if run is None:
            raise ValueError(f"Unknown eval run: {run_id}")
        run.status = "completed"
        run.metrics_json = json.dumps(metrics)
        run.failure_examples_json = json.dumps(failure_examples)
        run.completed_at = datetime.utcnow()
        db.flush()
        return run

    def get_run(self, db: Session, run_id: str) -> tuple[EvalRun | None, list[EvalResult]]:
        run = db.get(EvalRun, run_id)
        if run is None:
            return None, []
        statement = select(EvalResult).where(EvalResult.run_id == run_id)
        return run, list(db.scalars(statement))