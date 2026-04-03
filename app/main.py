from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.chat import router as chat_router
from app.api.routes.evaluation import router as evaluation_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.trace import router as trace_router
from app.core.config import Settings, get_settings
from app.core.container import AppContainer
from app.db.init_db import init_db
from app.db.session import create_session_factory
from app.repositories.chat_repository import ChatRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.evaluation_repository import EvaluationRepository
from app.services.agent.llm import LLMClient
from app.services.agent.service import KnowledgeOpsAgentService
from app.services.evaluation.service import EvaluationService
from app.services.ingestion.connectors import DocumentParser
from app.services.ingestion.service import IngestionService
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
    return AppContainer(
        settings=settings,
        session_factory=session_factory,
        embedding_service=embedding_service,
        retrieval_service=retrieval_service,
        ingestion_service=ingestion_service,
        agent_service=agent_service,
        evaluation_service=evaluation_service,
    )


def create_app(settings_override: Settings | None = None) -> FastAPI:
    settings = settings_override or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        container = create_container(settings)
        app.state.container = container
        init_db(container.session_factory)
        db = container.session_factory()
        try:
            container.evaluation_service.seed_default_cases(db)
            db.commit()
        finally:
            db.close()
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(knowledge_router)
    app.include_router(chat_router)
    app.include_router(trace_router)
    app.include_router(evaluation_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name}

    return app


app = create_app()