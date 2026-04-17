from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.chat_repository import ChatRepository
from app.schemas.auth import UserProfileRead
from app.schemas.chat import ChatMessageRead, FeedbackCreate, FeedbackRead, QueryRequest, QueryResponse, SessionRead
from app.schemas.trace import TraceRead, TraceSearchResult
from app.services.agent.llm import LLMClient
from app.services.agent.workflow import KnowledgeGraphBuilder
from app.services.retrieval.service import RetrievalService


class KnowledgeOpsAgentService:
    def __init__(
        self,
        *,
        chat_repository: ChatRepository,
        retrieval_service: RetrievalService,
        llm_client: LLMClient,
    ) -> None:
        self.chat_repository = chat_repository
        self.retrieval_service = retrieval_service
        self.llm_client = llm_client

    def query(self, db: Session, request: QueryRequest, *, current_user: UserProfileRead) -> QueryResponse:
        session = self.chat_repository.get_or_create_session(db, request.session_id, request.query, current_user.id)
        history_messages = self.chat_repository.list_messages(db, session.id)
        trace_id = str(uuid.uuid4())
        self.chat_repository.create_trace(
            db,
            trace_id=trace_id,
            session_id=session.id,
            user_id=current_user.id,
            user_role=current_user.role,
            query=request.query,
        )
        self.chat_repository.add_message(db, session_id=session.id, role="user", content=request.query, trace_id=trace_id)

        workflow = KnowledgeGraphBuilder(llm_client=self.llm_client, retrieval_service=self.retrieval_service).build(db)
        state = workflow.invoke(
            {
                "query": request.query,
                "session_id": session.id,
                "user_role": current_user.role,
                "top_k": request.top_k,
                "requested_tools": list(request.tool_sequence or []),
                "history": [{"role": msg.role, "content": msg.content} for msg in history_messages[-6:]],
                "trace_id": trace_id,
                "trace_steps": [],
            }
        )

        citations = [citation.model_dump() for citation in state.get("citations", [])]
        final_answer = str(state.get("final_answer", state.get("draft_answer", "")))
        debug_summary = dict(state.get("debug_summary", {}))
        self.chat_repository.add_trace_steps(db, trace_id, list(state.get("trace_steps", [])))
        self.chat_repository.finalize_trace(
            db,
            trace_id=trace_id,
            intent=str(state.get("intent", "qa")),
            next_action=str(state.get("next_action", "answer")),
            confidence=float(state.get("confidence", 0.0)),
            final_answer=final_answer,
            debug_summary=debug_summary,
        )
        self.chat_repository.add_message(
            db,
            session_id=session.id,
            role="assistant",
            content=final_answer,
            trace_id=trace_id,
            citations_json=json.dumps(citations),
        )
        db.commit()

        return QueryResponse(
            session_id=session.id,
            answer=final_answer,
            citations=list(state.get("citations", [])),
            confidence=float(state.get("confidence", 0.0)),
            trace_id=trace_id,
            next_action=str(state.get("next_action", "answer")),
            intent=str(state.get("intent", "qa")),
            tool_calls=list(state.get("tool_calls", [])),
            debug_summary=debug_summary,
        )

    def get_session(self, db: Session, session_id: str, *, current_user: UserProfileRead) -> SessionRead:
        session = self.chat_repository.get_session(db, session_id)
        if session is None or (current_user.role != "admin" and session.user_id != current_user.id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
        messages = self.chat_repository.list_messages(db, session_id)
        return SessionRead(
            id=session_id,
            messages=[
                ChatMessageRead(
                    role=message.role,
                    content=message.content,
                    trace_id=message.trace_id,
                    citations=json.loads(message.citations_json or "[]"),
                    created_at=message.created_at,
                )
                for message in messages
            ],
        )

    def add_feedback(self, db: Session, payload: FeedbackCreate, *, current_user: UserProfileRead) -> FeedbackRead:
        session = self.chat_repository.get_session(db, payload.session_id)
        if session is None or (current_user.role != "admin" and session.user_id != current_user.id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
        feedback = self.chat_repository.add_feedback(
            db,
            session_id=payload.session_id,
            trace_id=payload.trace_id,
            rating=payload.rating,
            corrected_answer=payload.corrected_answer,
            comment=payload.comment,
            include_in_eval=payload.include_in_eval,
        )
        db.commit()
        return FeedbackRead.model_validate(feedback)

    def get_trace(self, db: Session, trace_id: str) -> TraceRead | None:
        trace, steps = self.chat_repository.get_trace(db, trace_id)
        if trace is None:
            return None
        return TraceRead(
            trace_id=trace.trace_id,
            session_id=trace.session_id,
            query=trace.query,
            intent=trace.intent,
            next_action=trace.next_action,
            confidence=trace.confidence,
            final_answer=trace.final_answer,
            debug_summary=json.loads(trace.debug_summary_json or "{}"),
            created_at=trace.created_at,
            steps=steps,
        )

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
    ) -> list[TraceSearchResult]:
        return [
            TraceSearchResult(
                trace_id=trace.trace_id,
                session_id=trace.session_id,
                query=trace.query,
                user_role=trace.user_role,
                intent=trace.intent,
                next_action=trace.next_action,
                confidence=trace.confidence,
                created_at=trace.created_at,
                has_failure=has_failure,
            )
            for trace, has_failure in self.chat_repository.search_traces(
                db,
                intent=intent,
                next_action=next_action,
                user_role=user_role,
                failed_only=failed_only,
                created_after=created_after,
                created_before=created_before,
                limit=limit,
            )
        ]
