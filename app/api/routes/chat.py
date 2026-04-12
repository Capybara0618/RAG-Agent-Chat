from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_agent_service, get_current_user, get_db, require_roles
from app.schemas.auth import UserProfileRead
from app.schemas.chat import FeedbackCreate, FeedbackRead, QueryRequest, QueryResponse, SessionRead
from app.services.agent.service import KnowledgeOpsAgentService


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/query", response_model=QueryResponse)
def query_chat(
    payload: QueryRequest,
    db: Session = Depends(get_db),
    agent_service: KnowledgeOpsAgentService = Depends(get_agent_service),
    current_user: UserProfileRead = Depends(require_roles("manager", "procurement", "legal", "admin")),
) -> QueryResponse:
    return agent_service.query(db, payload.model_copy(update={"user_role": current_user.role}), current_user=current_user)


@router.get("/sessions/{session_id}", response_model=SessionRead)
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    agent_service: KnowledgeOpsAgentService = Depends(get_agent_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> SessionRead:
    session = agent_service.get_session(db, session_id, current_user=current_user)
    if not session.messages:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


@router.post("/feedback", response_model=FeedbackRead)
def create_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    agent_service: KnowledgeOpsAgentService = Depends(get_agent_service),
    current_user: UserProfileRead = Depends(get_current_user),
) -> FeedbackRead:
    return agent_service.add_feedback(db, payload, current_user=current_user)
