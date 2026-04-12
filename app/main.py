from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.evaluation import router as evaluation_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.projects import router as projects_router
from app.api.routes.trace import router as trace_router
from app.core.config import Settings, get_settings
from app.core.container import AppContainer
from app.db.init_db import init_db
from app.db.session import create_session_factory
from app.repositories.auth_repository import AuthRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.project_repository import ProjectRepository
from app.services.agent.llm import LLMClient
from app.services.agent.service import KnowledgeOpsAgentService
from app.services.auth_service import AuthService
from app.services.evaluation.service import EvaluationService
from app.services.ingestion.connectors import DocumentParser
from app.services.ingestion.service import IngestionService
from app.services.project_service import ProjectService
from app.services.retrieval.embeddings import EmbeddingService
from app.services.retrieval.service import RetrievalService


def create_container(settings: Settings) -> AppContainer:
    session_factory = create_session_factory(settings)
    embedding_service = EmbeddingService()
    document_repository = DocumentRepository()
    retrieval_service = RetrievalService(document_repository, embedding_service)
    ingestion_service = IngestionService(
        settings=settings,
        repository=document_repository,
        parser=DocumentParser(),
        embedding_service=embedding_service,
        session_factory=session_factory,
    )
    llm_client = LLMClient(
        api_base=settings.openai_api_base,
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )
    agent_service = KnowledgeOpsAgentService(
        chat_repository=ChatRepository(),
        retrieval_service=retrieval_service,
        llm_client=llm_client,
    )
    evaluation_service = EvaluationService(
        repository=EvaluationRepository(),
        agent_service=agent_service,
    )
    auth_service = AuthService(repository=AuthRepository())
    project_service = ProjectService(
        repository=ProjectRepository(),
        agent_service=agent_service,
    )
    return AppContainer(
        settings=settings,
        session_factory=session_factory,
        embedding_service=embedding_service,
        retrieval_service=retrieval_service,
        ingestion_service=ingestion_service,
        agent_service=agent_service,
        auth_service=auth_service,
        evaluation_service=evaluation_service,
        project_service=project_service,
    )


def create_app(settings_override: Settings | None = None) -> FastAPI:
    settings = settings_override or get_settings()
    container = create_container(settings)
    frontend_dir = Path(__file__).resolve().parents[1] / "frontend"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        app.state.container = container
        init_db(container.session_factory)

        db = container.session_factory()
        try:
            container.auth_service.seed_demo_users(db)
            container.evaluation_service.seed_default_cases(db)
        finally:
            db.close()

        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.container = container
    app.include_router(auth_router)
    app.include_router(knowledge_router)
    app.include_router(chat_router)
    app.include_router(trace_router)
    app.include_router(evaluation_router)
    app.include_router(projects_router)

    @app.middleware("http")
    async def disable_frontend_cache(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/app"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    if frontend_dir.exists():
        app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    @app.get("/")
    def root():
        return RedirectResponse(url="/app/")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name}

    return app


app = create_app()
