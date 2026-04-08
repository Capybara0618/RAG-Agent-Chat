from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import EvalCase, EvalResult, EvalRun


class EvaluationRepository:
    def list_cases(
        self,
        db: Session,
        *,
        task_types: list[str] | None = None,
        required_roles: list[str] | None = None,
        knowledge_domains: list[str] | None = None,
    ) -> list[EvalCase]:
        statement = select(EvalCase).order_by(EvalCase.created_at.asc())
        if task_types:
            statement = statement.where(EvalCase.task_type.in_(task_types))
        if required_roles:
            statement = statement.where(EvalCase.required_role.in_(required_roles))
        if knowledge_domains:
            statement = statement.where(EvalCase.knowledge_domain.in_(knowledge_domains))
        return list(db.scalars(statement))

    def get_cases(
        self,
        db: Session,
        case_ids: list[str],
        *,
        task_types: list[str] | None = None,
        required_roles: list[str] | None = None,
        knowledge_domains: list[str] | None = None,
    ) -> list[EvalCase]:
        if case_ids:
            statement = select(EvalCase).where(EvalCase.id.in_(case_ids)).order_by(EvalCase.created_at.asc())
            return list(db.scalars(statement))
        return self.list_cases(
            db,
            task_types=task_types,
            required_roles=required_roles,
            knowledge_domains=knowledge_domains,
        )

    def create_case(
        self,
        db: Session,
        *,
        question: str,
        expected_answer: str,
        expected_document_title: str,
        task_type: str,
        required_role: str,
        knowledge_domain: str,
    ) -> EvalCase:
        case = EvalCase(
            question=question,
            expected_answer=expected_answer,
            expected_document_title=expected_document_title,
            task_type=task_type,
            required_role=required_role,
            knowledge_domain=knowledge_domain,
        )
        db.add(case)
        db.flush()
        return case

    def create_run(self, db: Session, *, filters: dict[str, object]) -> EvalRun:
        run = EvalRun(filters_json=json.dumps(filters, ensure_ascii=False))
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
        returned_action: str,
        failure_tag: str,
        trace_id: str,
    ) -> EvalResult:
        result = EvalResult(
            run_id=run_id,
            case_id=case_id,
            answer=answer,
            score_recall=score_recall,
            score_citation=score_citation,
            score_safety=score_safety,
            passed=passed,
            notes=notes,
            returned_action=returned_action,
            failure_tag=failure_tag,
            trace_id=trace_id,
        )
        db.add(result)
        db.flush()
        return result

    def finalize_run(
        self,
        db: Session,
        *,
        run_id: str,
        metrics: dict[str, float],
        failure_examples: list[dict[str, str | float]],
        failure_tag_counts: dict[str, int],
    ) -> EvalRun:
        run = db.get(EvalRun, run_id)
        if run is None:
            raise ValueError(f"Unknown eval run: {run_id}")
        run.status = "completed"
        run.metrics_json = json.dumps(metrics, ensure_ascii=False)
        run.failure_examples_json = json.dumps(failure_examples, ensure_ascii=False)
        run.failure_tag_counts_json = json.dumps(failure_tag_counts, ensure_ascii=False)
        run.completed_at = datetime.utcnow()
        db.flush()
        return run

    def get_run(self, db: Session, run_id: str) -> tuple[EvalRun | None, list[EvalResult]]:
        run = db.get(EvalRun, run_id)
        if run is None:
            return None, []
        statement = select(EvalResult).where(EvalResult.run_id == run_id)
        return run, list(db.scalars(statement))
