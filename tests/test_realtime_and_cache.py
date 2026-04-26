from __future__ import annotations

from collections import OrderedDict
from queue import Empty

import pytest

from app.services.ingestion.service import IngestionService
from app.services.retrieval.embeddings import EmbeddingService
from app.services.retrieval.service import RetrievedChunk, RetrievalService


class _DummyVector(list):
    def tolist(self):
        return list(self)


class _DummyEmbeddingModel:
    def __init__(self) -> None:
        self.calls = 0

    def encode(self, texts, **kwargs):
        self.calls += 1
        return [_DummyVector([1.0, 0.0, 0.0])]


class _FakeReranker:
    model_name = "fake-reranker"

    def rerank(self, *, candidates, top_k, **kwargs):
        return candidates[:top_k], {
            "rerank_strategy": "fake",
            "rerank_input_count": len(candidates),
            "rerank_output_count": len(candidates[:top_k]),
            "cross_encoder_enabled": False,
            "cross_encoder_active": False,
        }


class _FakeRedisBackend:
    def __init__(self) -> None:
        self.storage: dict[str, dict[str, object]] = {}
        self._hits = 0
        self._misses = 0
        self._writes = 0

    @property
    def available(self) -> bool:
        return True

    def get_json(self, key: str):
        value = self.storage.get(key)
        if value is None:
            self._misses += 1
            return None
        self._hits += 1
        return value

    def set_json(self, key: str, payload: dict[str, object], ttl_seconds: float) -> bool:
        self.storage[key] = payload
        self._writes += 1
        return True

    def stats(self) -> dict[str, object]:
        return {
            "backend": "redis",
            "enabled": True,
            "available": True,
            "hits": self._hits,
            "misses": self._misses,
            "writes": self._writes,
            "last_error": "",
        }


def test_embedding_service_reuses_cached_vectors():
    service = EmbeddingService(model_name="dummy")
    service._model = _DummyEmbeddingModel()

    first = service.embed_text("same text")
    second = service.embed_text("same text")

    assert first == second
    assert service._model.calls == 1
    assert service.cache_stats()["hits"] == 1


def test_retrieval_service_reports_cache_hit():
    retrieval = RetrievalService.__new__(RetrievalService)
    retrieval.embedding_service = EmbeddingService()
    retrieval.reranker = _FakeReranker()
    retrieval.bm25_k1 = 1.2
    retrieval.bm25_b = 0.75
    retrieval.rrf_k = 60
    retrieval.rrf_weights = {"bm25": 1.0, "semantic": 0.2}
    retrieval.cache_backend = None
    retrieval._local_embedding_cache = {}
    retrieval.retrieval_cache_ttl_seconds = 30.0
    retrieval.retrieval_cache_max_entries = 16
    retrieval._retrieval_cache = OrderedDict()
    retrieval._retrieval_cache_hits = 0
    retrieval._retrieval_cache_misses = 0
    retrieval._load_accessible_chunks = lambda db, user_role: []
    retrieval._filter_accessible_chunks_for_task = lambda records, **kwargs: records
    retrieval._bm25_retrieve = lambda **kwargs: [
        RetrievedChunk(
            chunk_id="c1",
            document_id="d1",
            document_title="采购核心-供应商准入办法.md",
            source_type="markdown",
            location="1",
            content="供应商需要主体信息。",
            heading="准入",
            score=1.0,
            score_breakdown={"bm25": 1.0},
        )
    ]
    retrieval._semantic_retrieve = lambda db, **kwargs: []
    retrieval._merge_candidates_rrf = lambda bm25_candidates, semantic_candidates: bm25_candidates

    first_chunks, first_debug = retrieval.retrieve(
        None,
        query="供应商主体信息是否齐全",
        user_role="procurement",
        top_k=1,
        plan={"task_mode": "knowledge_qa"},
    )
    second_chunks, second_debug = retrieval.retrieve(
        None,
        query="供应商主体信息是否齐全",
        user_role="procurement",
        top_k=1,
        plan={"task_mode": "knowledge_qa"},
    )

    assert first_chunks[0].document_title == second_chunks[0].document_title
    assert first_debug["cache"]["hit"] is False
    assert second_debug["cache"]["hit"] is True
    assert second_debug["cache"]["memory_hits"] >= 1


def test_retrieval_service_can_use_redis_cache_backend():
    retrieval = RetrievalService.__new__(RetrievalService)
    retrieval.embedding_service = EmbeddingService()
    retrieval.reranker = _FakeReranker()
    retrieval.bm25_k1 = 1.2
    retrieval.bm25_b = 0.75
    retrieval.rrf_k = 60
    retrieval.rrf_weights = {"bm25": 1.0, "semantic": 0.2}
    retrieval.cache_backend = _FakeRedisBackend()
    retrieval._local_embedding_cache = {}
    retrieval.retrieval_cache_ttl_seconds = 30.0
    retrieval.retrieval_cache_max_entries = 16
    retrieval._retrieval_cache = OrderedDict()
    retrieval._retrieval_cache_hits = 0
    retrieval._retrieval_cache_misses = 0
    retrieval._load_accessible_chunks = lambda db, user_role: []
    retrieval._filter_accessible_chunks_for_task = lambda records, **kwargs: records
    retrieval._bm25_retrieve = lambda **kwargs: [
        RetrievedChunk(
            chunk_id="c1",
            document_id="d1",
            document_title="法务核心-合同审查红线指引.md",
            source_type="markdown",
            location="1",
            content="责任上限不得被明显弱化。",
            heading="红线",
            score=1.0,
            score_breakdown={"bm25": 1.0},
        )
    ]
    retrieval._semantic_retrieve = lambda db, **kwargs: []
    retrieval._merge_candidates_rrf = lambda bm25_candidates, semantic_candidates: bm25_candidates

    _, first_debug = retrieval.retrieve(
        None,
        query="责任上限被改成三个月服务费是否合理",
        user_role="legal",
        top_k=1,
        plan={"task_mode": "legal_contract_review"},
    )
    _, second_debug = retrieval.retrieve(
        None,
        query="责任上限被改成三个月服务费是否合理",
        user_role="legal",
        top_k=1,
        plan={"task_mode": "legal_contract_review"},
    )

    assert first_debug["cache"]["hit"] is False
    assert second_debug["cache"]["hit"] is True
    assert second_debug["cache"]["source"] == "redis"
    assert second_debug["cache"]["redis"]["hits"] >= 1


def test_ingestion_service_task_event_subscription_receives_progress():
    service = IngestionService.__new__(IngestionService)
    service._task_event_history = {}
    service._task_subscribers = {}
    from threading import Lock

    service._task_event_lock = Lock()
    subscriber = service.subscribe_task_events("task-1")

    service._publish_task_event(
        "task-1",
        event="task_progress",
        stage="embedding",
        message="正在生成向量：2/4。",
        task={"id": "task-1", "status": "indexing"},
        progress={"current": 2, "total": 4, "unit": "chunks"},
    )

    payload = subscriber.get(timeout=1.0)
    service.unsubscribe_task_events("task-1", subscriber)

    assert payload["stage"] == "embedding"
    assert payload["progress"]["current"] == 2
    with pytest.raises(Empty):
        subscriber.get_nowait()
