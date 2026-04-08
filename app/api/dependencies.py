from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.container import AppContainer
from app.services.agent.service import KnowledgeOpsAgentService
from app.services.evaluation.service import EvaluationService
from app.services.ingestion.service import IngestionService
from app.services.project_service import ProjectService


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_db(container: AppContainer = Depends(get_container)) -> Generator[Session, None, None]:
    db = container.session_factory()
    try:
        yield db
    finally:
        db.close()


def get_ingestion_service(container: AppContainer = Depends(get_container)) -> IngestionService:
    return container.ingestion_service


def get_agent_service(container: AppContainer = Depends(get_container)) -> KnowledgeOpsAgentService:
    return container.agent_service


def get_evaluation_service(container: AppContainer = Depends(get_container)) -> EvaluationService:
    return container.evaluation_service


def get_project_service(container: AppContainer = Depends(get_container)) -> ProjectService:
    return container.project_service
