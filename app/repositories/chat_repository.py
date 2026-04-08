from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session

from app.models.entities import ChatMessage, ChatSession, Feedback, TraceRecord, TraceStep


class ChatRepository:
    def get_or_create_session(self, db: Session, session_id: str | None, seed_title: str) -> ChatSession:
        if session_id:
            existing = db.get(ChatSession, session_id)
            if existing:
                return existing

        session = ChatSession(id=session_id or str(uuid.uuid4()), title=seed_title[:80] or "New Session")
        db.add(session)
        db.flush()
        return session

    def list_messages(self, db: Session, session_id: str) -> list[ChatMessage]:
        statement = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc())
        return list(db.scalars(statement))

    def add_message(
        self,
        db: Session,
        *,
        session_id: str,
        role: str,
        content: str,
        trace_id: str = "",
        citations_json: str = "[]",
    ) -> ChatMessage:
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            trace_id=trace_id,
            citations_json=citations_json,
        )
        db.add(message)
        db.flush()
        return message

    def create_trace(self, db: Session, *, trace_id: str, session_id: str, user_role: str, query: str) -> TraceRecord:
        trace = TraceRecord(trace_id=trace_id, session_id=session_id, user_role=user_role, query=query)
        db.add(trace)
        db.flush()
        return trace

    def add_trace_steps(self, db: Session, trace_id: str, steps: list[dict[str, object]]) -> None:
        for step in steps:
            db.add(
                TraceStep(
                    trace_id=trace_id,
                    node_name=str(step["node_name"]),
                    input_summary=str(step.get("input_summary", "")),
                    output_summary=json.dumps(step.get("output_summary", ""), ensure_ascii=False)
                    if isinstance(step.get("output_summary", ""), (dict, list))
                    else str(step.get("output_summary", "")),
                    latency_ms=float(step.get("latency_ms", 0.0)),
                    success=bool(step.get("success", True)),
                )
            )
        db.flush()

    def finalize_trace(
        self,
        db: Session,
        *,
        trace_id: str,
        intent: str,
        next_action: str,
        confidence: float,
        final_answer: str,
        debug_summary: dict[str, object] | None = None,
    ) -> None:
        trace = db.get(TraceRecord, trace_id)
        if trace is None:
            return
        trace.intent = intent
        trace.next_action = next_action
        trace.confidence = confidence
        trace.final_answer = final_answer
        trace.debug_summary_json = json.dumps(debug_summary or {}, ensure_ascii=False)
        db.flush()

    def get_trace(self, db: Session, trace_id: str) -> tuple[TraceRecord | None, list[TraceStep]]:
        trace = db.get(TraceRecord, trace_id)
        if trace is None:
            return None, []
        statement = select(TraceStep).where(TraceStep.trace_id == trace_id).order_by(TraceStep.created_at.asc())
        return trace, list(db.scalars(statement))

    def search_traces(
        self,
        db: Session,
        *,
        intent: str | None = None,
        next_action: str | None = None,
        user_role: str | None = None,
        failed_only: bool = False,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 50,
    ) -> list[tuple[TraceRecord, bool]]:
        statement = select(TraceRecord).order_by(TraceRecord.created_at.desc()).limit(limit)
        conditions = []
        if intent:
            conditions.append(TraceRecord.intent == intent)
        if next_action:
            conditions.append(TraceRecord.next_action == next_action)
        if user_role:
            conditions.append(TraceRecord.user_role == user_role)
        if created_after:
            conditions.append(TraceRecord.created_at >= created_after)
        if created_before:
            conditions.append(TraceRecord.created_at <= created_before)
        if failed_only:
            failing_steps = exists(
                select(TraceStep.id).where(and_(TraceStep.trace_id == TraceRecord.trace_id, TraceStep.success.is_(False)))
            )
            conditions.append((TraceRecord.next_action != "answer") | failing_steps)
        if conditions:
            statement = statement.where(*conditions)

        traces = list(db.scalars(statement))
        results: list[tuple[TraceRecord, bool]] = []
        for trace in traces:
            has_failure = trace.next_action != "answer" or bool(
                db.scalar(
                    select(TraceStep.id).where(
                        and_(TraceStep.trace_id == trace.trace_id, TraceStep.success.is_(False))
                    )
                )
            )
            results.append((trace, has_failure))
        return results

    def add_feedback(
        self,
        db: Session,
        *,
        session_id: str,
        trace_id: str,
        rating: int,
        corrected_answer: str,
        comment: str,
        include_in_eval: bool,
    ) -> Feedback:
        trace = db.get(TraceRecord, trace_id)
        candidate_case = {}
        if trace is not None:
            candidate_case = {
                "question": trace.query,
                "expected_answer": corrected_answer or trace.final_answer,
                "task_type": trace.intent or "qa",
                "required_role": trace.user_role,
                "trace_id": trace_id,
            }
        feedback = Feedback(
            session_id=session_id,
            trace_id=trace_id,
            rating=rating,
            corrected_answer=corrected_answer,
            comment=comment,
            include_in_eval=include_in_eval,
            review_status="pending" if include_in_eval else "ignored",
            candidate_case_json=json.dumps(candidate_case, ensure_ascii=False),
        )
        db.add(feedback)
        db.flush()
        return feedback
