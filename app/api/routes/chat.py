from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_agent_service, get_db
from app.schemas.chat import FeedbackCreate, FeedbackRead, QueryRequest, QueryResponse, SessionRead
from app.services.agent.service import KnowledgeOpsAgentService


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/query", response_model=QueryResponse)
def query_chat(
    payload: QueryRequest,
    db: Session = Depends(get_db),
    agent_service: KnowledgeOpsAgentService = Depends(get_agent_service),
) -> QueryResponse:
    return agent_service.query(db, payload)


@router.get("/sessions/{session_id}", response_model=SessionRead)
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    agent_service: KnowledgeOpsAgentService = Depends(get_agent_service),
) -> SessionRead:
    session = agent_service.get_session(db, session_id)
    if not session.messages:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


@router.post("/feedback", response_model=FeedbackRead)
def create_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    agent_service: KnowledgeOpsAgentService = Depends(get_agent_service),
) -> FeedbackRead:
    return agent_service.add_feedback(db, payload)