from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.container import AppContainer
from app.schemas.auth import UserProfileRead
from app.services.agent.service import KnowledgeOpsAgentService
from app.services.auth_service import AuthService
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


def get_auth_service(container: AppContainer = Depends(get_container)) -> AuthService:
    return container.auth_service


def get_evaluation_service(container: AppContainer = Depends(get_container)) -> EvaluationService:
    return container.evaluation_service


def get_project_service(container: AppContainer = Depends(get_container)) -> ProjectService:
    return container.project_service


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserProfileRead:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录。")
    return auth_service.get_user_by_token(db, authorization.split(" ", 1)[1])


def require_roles(*allowed_roles: str):
    def dependency(current_user: UserProfileRead = Depends(get_current_user)) -> UserProfileRead:
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号没有访问权限。")
        return current_user

    return dependency
