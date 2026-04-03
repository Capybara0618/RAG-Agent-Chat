from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_agent_service, get_db
from app.schemas.trace import TraceRead
from app.services.agent.service import KnowledgeOpsAgentService


router = APIRouter(prefix="/trace", tags=["trace"])


@router.get("/{trace_id}", response_model=TraceRead)
def get_trace(
    trace_id: str,
    db: Session = Depends(get_db),
    agent_service: KnowledgeOpsAgentService = Depends(get_agent_service),
) -> TraceRead:
    trace = agent_service.get_trace(db, trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return trace