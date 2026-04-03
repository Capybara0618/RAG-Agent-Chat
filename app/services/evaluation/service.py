from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.repositories.evaluation_repository import EvaluationRepository
from app.schemas.chat import QueryRequest
from app.schemas.evaluation import EvalRunRead
from app.services.agent.service import KnowledgeOpsAgentService


class EvaluationService:
    def __init__(self, *, repository: EvaluationRepository, agent_service: KnowledgeOpsAgentService) -> None:
        self.repository = repository
        self.agent_service = agent_service

    def seed_default_cases(self, db: Session) -> None:
        if self.repository.list_cases(db):
            return
        defaults = [
            {
                "question": "What should a new employee complete before receiving production access?",
                "expected_answer": "Training and manager approval are required before production access.",
                "expected_document_title": "sample_handbook.md",
                "task_type": "support",
                "required_role": "employee",
            },
            {
                "question": "Compare onboarding requirements with remote access requirements.",
                "expected_answer": "Both require approved steps, but remote access includes MFA and device compliance.",
                "expected_document_title": "sample_policy.md",
                "task_type": "compare",
                "required_role": "employee",
            },
            {
                "question": "What is the first step in the incident workflow?",
                "expected_answer": "Acknowledge the alert and classify severity.",
                "expected_document_title": "sample_handbook.md",
                "task_type": "workflow",
                "required_role": "employee",
            },
        ]
        for case in defaults:
            self.repository.create_case(db, **case)
        db.commit()

    def run(self, db: Session, case_ids: list[str]) -> EvalRunRead:
        cases = self.repository.get_cases(db, case_ids)
        run = self.repository.create_run(db)
        db.commit()

        recall_scores: list[float] = []
        citation_scores: list[float] = []
        safety_scores: list[float] = []
        failures: list[dict[str, str | float]] = []

        for case in cases:
            response = self.agent_service.query(
                db,
                QueryRequest(
                    query=case.question,
                    session_id=f"eval-{run.id}-{case.id}",
                    user_role=case.required_role,
                    top_k=5,
                ),
            )
            retrieved_titles = {citation.document_title for citation in response.citations}
            recall = 1.0 if case.expected_document_title in retrieved_titles else 0.0
            citation = 1.0 if response.citations else 0.0
            safety = 1.0 if response.next_action in {"answer", "clarify", "refuse"} else 0.0
            passed = recall == 1.0 and citation == 1.0 and safety == 1.0
            notes = "grounded" if passed else "inspect retrieval or citation coverage"

            recall_scores.append(recall)
            citation_scores.append(citation)
            safety_scores.append(safety)
            if not passed:
                failures.append(
                    {
                        "question": case.question,
                        "expected_document_title": case.expected_document_title,
                        "returned_action": response.next_action,
                        "confidence": response.confidence,
                    }
                )

            self.repository.add_result(
                db,
                run_id=run.id,
                case_id=case.id,
                answer=response.answer,
                score_recall=recall,
                score_citation=citation,
                score_safety=safety,
                passed=passed,
                notes=notes,
            )
            db.commit()

        metrics = {
            "recall_at_k": round(sum(recall_scores) / max(len(recall_scores), 1), 2),
            "citation_coverage": round(sum(citation_scores) / max(len(citation_scores), 1), 2),
            "safety_rate": round(sum(safety_scores) / max(len(safety_scores), 1), 2),
        }
        run = self.repository.finalize_run(db, run_id=run.id, metrics=metrics, failure_examples=failures[:10])
        db.commit()
        _, results = self.repository.get_run(db, run.id)
        return EvalRunRead(
            id=run.id,
            status=run.status,
            metrics=json.loads(run.metrics_json or "{}"),
            failure_examples=json.loads(run.failure_examples_json or "[]"),
            result_count=len(results),
            created_at=run.created_at,
            completed_at=run.completed_at,
        )

    def get_run(self, db: Session, run_id: str) -> EvalRunRead | None:
        run, results = self.repository.get_run(db, run_id)
        if run is None:
            return None
        return EvalRunRead(
            id=run.id,
            status=run.status,
            metrics=json.loads(run.metrics_json or "{}"),
            failure_examples=json.loads(run.failure_examples_json or "[]"),
            result_count=len(results),
            created_at=run.created_at,
            completed_at=run.completed_at,
        )