from __future__ import annotations

import json
import uuid
from collections import Counter

from sqlalchemy.orm import Session

from app.models.entities import EvalFailureTag
from app.repositories.evaluation_repository import EvaluationRepository
from app.schemas.auth import UserProfileRead
from app.schemas.chat import QueryRequest
from app.schemas.evaluation import EvalCaseCreate, EvalCaseRead, EvalResultRead, EvalRunRead, EvalRunRequest
from app.services.agent.service import KnowledgeOpsAgentService


class EvaluationService:
    def __init__(self, *, repository: EvaluationRepository, agent_service: KnowledgeOpsAgentService) -> None:
        self.repository = repository
        self.agent_service = agent_service

    def seed_default_cases(self, db: Session) -> None:
        # The procurement benchmark now lives in scripts/eval_procurement_ablation.py
        # because it evaluates structured supplier-review flows, not free-form Q&A.
        db.commit()

    def list_cases(
        self,
        db: Session,
        *,
        task_types: list[str] | None = None,
        required_roles: list[str] | None = None,
        knowledge_domains: list[str] | None = None,
    ) -> list[EvalCaseRead]:
        return [
            EvalCaseRead.model_validate(case)
            for case in self.repository.list_cases(
                db,
                task_types=task_types,
                required_roles=required_roles,
                knowledge_domains=knowledge_domains,
            )
        ]

    def create_case(self, db: Session, payload: EvalCaseCreate) -> EvalCaseRead:
        case = self.repository.create_case(db, **payload.model_dump())
        db.commit()
        return EvalCaseRead.model_validate(case)

    def run(self, db: Session, payload: EvalRunRequest) -> EvalRunRead:
        filters = {
            "case_ids": payload.case_ids,
            "task_types": payload.task_types,
            "required_roles": payload.required_roles,
            "knowledge_domains": payload.knowledge_domains,
        }
        cases = self.repository.get_cases(
            db,
            payload.case_ids,
            task_types=payload.task_types,
            required_roles=payload.required_roles,
            knowledge_domains=payload.knowledge_domains,
        )
        run = self.repository.create_run(db, filters=filters)
        db.commit()

        recall_scores: list[float] = []
        citation_scores: list[float] = []
        action_scores: list[float] = []
        refusal_scores: list[float] = []
        failures: list[dict[str, str | float]] = []
        failure_counter: Counter[str] = Counter()

        for case in cases:
            response = self.agent_service.query(
                db,
                QueryRequest(query=case.question, session_id=self._build_eval_session_id(run.id, case.id), top_k=5),
                current_user=UserProfileRead(
                    id=f"eval-{case.required_role}",
                    username=f"eval-{case.required_role}",
                    display_name=f"Eval {case.required_role}",
                    role=case.required_role,
                    department="evaluation",
                    status="active",
                ),
            )
            retrieved_titles = {citation.document_title for citation in response.citations}
            recall = 1.0 if case.expected_document_title in retrieved_titles else 0.0
            citation = 1.0 if response.citations else 0.0
            action_accuracy = 1.0 if response.next_action in {"answer", "clarify", "refuse"} else 0.0
            refusal_rate = 1.0 if (not response.citations and response.next_action in {"clarify", "refuse"}) else 0.0
            passed = recall == 1.0 and citation == 1.0 and action_accuracy == 1.0
            failure_tag = self._tag_failure(response, case, recall, citation)
            notes = "grounded" if passed else failure_tag

            recall_scores.append(recall)
            citation_scores.append(citation)
            action_scores.append(action_accuracy)
            refusal_scores.append(refusal_rate)
            if failure_tag:
                failure_counter[failure_tag] += 1
            if not passed:
                failures.append(
                    {
                        "question": case.question,
                        "expected_document_title": case.expected_document_title,
                        "returned_action": response.next_action,
                        "confidence": response.confidence,
                        "failure_tag": failure_tag,
                    }
                )

            self.repository.add_result(
                db,
                run_id=run.id,
                case_id=case.id,
                answer=response.answer,
                score_recall=recall,
                score_citation=citation,
                score_safety=action_accuracy,
                passed=passed,
                notes=notes,
                returned_action=response.next_action,
                failure_tag=failure_tag,
                trace_id=response.trace_id,
            )
            db.commit()

        metrics = {
            "recall_at_k": round(sum(recall_scores) / max(len(recall_scores), 1), 2),
            "citation_coverage": round(sum(citation_scores) / max(len(citation_scores), 1), 2),
            "answer_action_accuracy": round(sum(action_scores) / max(len(action_scores), 1), 2),
            "insufficient_evidence_refusal_rate": round(sum(refusal_scores) / max(len(refusal_scores), 1), 2),
        }
        self.repository.finalize_run(
            db,
            run_id=run.id,
            metrics=metrics,
            failure_examples=failures[:10],
            failure_tag_counts=dict(failure_counter),
        )
        db.commit()
        return self.get_run(db, run.id) or EvalRunRead(
            id=run.id,
            status="completed",
            metrics=metrics,
            failure_examples=failures[:10],
            failure_tag_counts=dict(failure_counter),
            result_count=len(cases),
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
            failure_tag_counts=json.loads(run.failure_tag_counts_json or "{}"),
            result_count=len(results),
            created_at=run.created_at,
            completed_at=run.completed_at,
            filters=json.loads(run.filters_json or "{}"),
            results=[
                EvalResultRead(
                    case_id=result.case_id,
                    answer=result.answer,
                    score_recall=result.score_recall,
                    score_citation=result.score_citation,
                    score_safety=result.score_safety,
                    passed=result.passed,
                    notes=result.notes,
                    returned_action=result.returned_action,
                    failure_tag=result.failure_tag,
                    trace_id=result.trace_id,
                )
                for result in results
            ],
        )

    @staticmethod
    def _build_eval_session_id(run_id: str, case_id: str) -> str:
        return str(uuid.uuid5(uuid.UUID(run_id), case_id))

    @staticmethod
    def _tag_failure(response, case, recall: float, citation: float) -> str:
        if response.next_action == "refuse" and not response.citations:
            return (
                EvalFailureTag.permission_filtered.value
                if case.required_role == "guest"
                else EvalFailureTag.retrieval_miss.value
            )
        if recall == 0.0:
            return EvalFailureTag.retrieval_miss.value
        if citation == 0.0:
            return EvalFailureTag.citation_gap.value
        if response.next_action != "answer":
            return EvalFailureTag.conflict_unhandled.value
        return ""
