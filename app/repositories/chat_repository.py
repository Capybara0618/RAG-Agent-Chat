from __future__ import annotations

import uuid

from sqlalchemy import select
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
                    output_summary=str(step.get("output_summary", "")),
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
    ) -> None:
        trace = db.get(TraceRecord, trace_id)
        if trace is None:
            return
        trace.intent = intent
        trace.next_action = next_action
        trace.confidence = confidence
        trace.final_answer = final_answer
        db.flush()

    def get_trace(self, db: Session, trace_id: str) -> tuple[TraceRecord | None, list[TraceStep]]:
        trace = db.get(TraceRecord, trace_id)
        if trace is None:
            return None, []
        statement = select(TraceStep).where(TraceStep.trace_id == trace_id).order_by(TraceStep.created_at.asc())
        return trace, list(db.scalars(statement))

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
        feedback = Feedback(
            session_id=session_id,
            trace_id=trace_id,
            rating=rating,
            corrected_answer=corrected_answer,
            comment=comment,
            include_in_eval=include_in_eval,
        )
        db.add(feedback)
        db.flush()
        return feedback