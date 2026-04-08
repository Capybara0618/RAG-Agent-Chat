from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_agent_service, get_db
from app.schemas.trace import TraceRead, TraceSearchResult
from app.services.agent.service import KnowledgeOpsAgentService


router = APIRouter(prefix="/trace", tags=["trace"])


@router.get("/search", response_model=list[TraceSearchResult])
def search_traces(
    intent: str | None = Query(default=None),
    next_action: str | None = Query(default=None),
    user_role: str | None = Query(default=None),
    failed_only: bool = Query(default=False),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    agent_service: KnowledgeOpsAgentService = Depends(get_agent_service),
) -> list[TraceSearchResult]:
    return agent_service.search_traces(
        db,
        intent=intent,
        next_action=next_action,
        user_role=user_role,
        failed_only=failed_only,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
    )


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
