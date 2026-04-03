from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.services.agent.service import KnowledgeOpsAgentService
from app.services.evaluation.service import EvaluationService
from app.services.ingestion.service import IngestionService
from app.services.retrieval.embeddings import EmbeddingService
from app.services.retrieval.service import RetrievalService


@dataclass
class AppContainer:
    settings: Settings
    session_factory: sessionmaker
    embedding_service: EmbeddingService
    retrieval_service: RetrievalService
    ingestion_service: IngestionService
    agent_service: KnowledgeOpsAgentService
    evaluation_service: EvaluationService