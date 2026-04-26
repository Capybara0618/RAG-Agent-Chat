from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from time import perf_counter

from sqlalchemy.orm import Session

from app.core.security import can_access
from app.repositories.document_repository import DocumentRepository
from app.schemas.common import Citation
from app.services.cache_backend import RedisJsonCacheBackend
from app.services.retrieval.embeddings import EmbeddingService, tokenize_text
from app.services.retrieval.rerankers import CrossEncoderReranker, _select_top_chunks


CLAUSE_PATTERNS = {
    "责任上限": ("liability cap", "limitation of liability", "责任上限", "赔偿上限"),
    "赔偿责任": ("indemnity", "赔偿", "赔偿责任"),
    "审计权": ("audit right", "audit rights", "审计权", "审计访问"),
    "数据处理": ("data processing", "dpa", "个人信息", "数据处理", "数据出境"),
    "安全事件通知": ("security incident", "breach notice", "安全事件", "通知时限"),
    "分包限制": ("subcontractor", "sub-processor", "分包", "转包"),
    "便利终止": ("termination for convenience", "convenience termination", "便利终止", "无因终止"),
    "付款条款": ("payment terms", "invoice", "net 45", "付款条款", "发票"),
    "服务水平": ("sla", "service level", "service credit", "服务水平", "服务赔偿"),
}

INSTRUCTION_PREFIXES = (
    "你是",
    "请基于",
    "请结合",
    "请判断",
    "请输出",
    "请给出",
    "你的任务",
    "重点回答",
    "请说明",
    "respond with",
    "return a",
    "you are",
)


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_title: str
    source_type: str
    location: str
    content: str
    heading: str
    score: float
    score_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class ChunkRecord:
    chunk_id: str
    document_id: str
    document_title: str
    document_tags: str
    source_type: str
    location: str
    content: str
    heading: str
    searchable_text: str
    tokens: list[str]


class RetrievalService:
    def __init__(
        self,
        repository: DocumentRepository,
        embedding_service: EmbeddingService,
        *,
        cache_backend: RedisJsonCacheBackend | None = None,
        cache_ttl_seconds: float = 30.0,
        reranker_model: str = "BAAI/bge-reranker-base",
        reranker_device: str = "cpu",
        reranker_enabled: bool = True,
    ) -> None:
        self.repository = repository
        self.embedding_service = embedding_service
        self.cache_backend = cache_backend
        self.reranker = CrossEncoderReranker(
            model_name=reranker_model,
            device=reranker_device,
            enabled=reranker_enabled,
        )
        self.bm25_k1 = 1.2
        self.bm25_b = 0.75
        self.rrf_k = 60
        self.rrf_weights = {
            "bm25": 1.0,
            "semantic": 0.2,
        }
        self._local_embedding_cache: dict[str, list[float]] = {}
        self.retrieval_cache_ttl_seconds = cache_ttl_seconds
        self.retrieval_cache_max_entries = 128
        self._retrieval_cache: OrderedDict[str, tuple[float, list[RetrievedChunk], dict[str, object]]] = OrderedDict()
        self._retrieval_cache_hits = 0
        self._retrieval_cache_misses = 0

    def rewrite_query(self, query: str) -> str:
        normalized = " ".join(query.strip().split())
        if not normalized:
            return ""

        structured_rewrite = self._rewrite_structured_procurement_query(query)
        if structured_rewrite:
            return structured_rewrite
        legal_rewrite = self._rewrite_structured_legal_query(query)
        if legal_rewrite:
            return legal_rewrite

        fragments = self._extract_query_fragments(normalized)
        deduped = self._dedupe_fragments(fragments)
        concise = " ".join(deduped[:5]).strip()
        if not concise:
            return normalized[:240]
        if concise == normalized:
            return concise
        if len(concise) >= max(24, int(len(normalized) * 0.9)):
            return normalized[:240]
        return concise

    def build_query_variants(self, query: str, plan: dict[str, object] | None = None) -> list[str]:
        variants = [query.strip()]
        rewritten = self.rewrite_query(query)
        if rewritten and rewritten not in variants:
            variants.append(rewritten)

        if plan:
            for variant in plan.get("query_variants", []):
                variant_text = str(variant).strip()
                if variant_text and variant_text not in variants:
                    variants.append(variant_text)
        return [variant[:240] for variant in variants if variant]

    def retrieve(
        self,
        db: Session,
        *,
        query: str,
        user_role: str,
        top_k: int,
        plan: dict[str, object] | None = None,
    ) -> tuple[list[RetrievedChunk], dict[str, object]]:
        total_started = perf_counter()
        rewrite_started = perf_counter()
        variants = self.build_query_variants(query, plan)
        rewrite_ms = round((perf_counter() - rewrite_started) * 1000, 2)
        task_mode = str((plan or {}).get("task_mode", "knowledge_qa"))
        source_type_hints = [str(item) for item in (plan or {}).get("source_type_hints", [])]
        document_hints = [str(item) for item in (plan or {}).get("document_hints", [])]
        domain_labels = [str(item) for item in (plan or {}).get("domain_labels", [])]
        cache_key = self._build_retrieval_cache_key(
            query=query,
            user_role=user_role,
            top_k=top_k,
            task_mode=task_mode,
            query_variants=variants,
            source_type_hints=source_type_hints,
            document_hints=document_hints,
            domain_labels=domain_labels,
        )
        cached, cache_source = self._get_cached_retrieval(cache_key)
        if cached is not None:
            cached_chunks, cached_debug = cached
            return copy.deepcopy(cached_chunks), {
                **cached_debug,
                "latency_ms": {
                    "rewrite_ms": rewrite_ms,
                    "cache_lookup_ms": round((perf_counter() - total_started) * 1000, 2),
                    "load_chunks_ms": 0.0,
                    "bm25_ms": 0.0,
                    "semantic_ms": 0.0,
                    "rrf_ms": 0.0,
                    "rerank_ms": 0.0,
                    "total_ms": round((perf_counter() - total_started) * 1000, 2),
                },
                "cache": {
                    "enabled": True,
                    "hit": True,
                    "source": cache_source,
                    "ttl_seconds": self.retrieval_cache_ttl_seconds,
                    **self.cache_stats(),
                },
            }

        load_started = perf_counter()
        accessible_chunks = self._load_accessible_chunks(db, user_role=user_role)
        accessible_chunks = self._filter_accessible_chunks_for_task(
            accessible_chunks,
            task_mode=task_mode,
            document_hints=document_hints,
        )
        load_chunks_ms = round((perf_counter() - load_started) * 1000, 2)
        rerank_k = int((plan or {}).get("rerank_k", max(top_k * 3, 10)))
        candidate_limit = max(min(rerank_k, top_k * 4), top_k + 4, 8)

        bm25_started = perf_counter()
        bm25_candidates = self._bm25_retrieve(
            variants=variants,
            records=accessible_chunks,
            candidate_limit=candidate_limit,
            source_type_hints=source_type_hints,
            document_hints=document_hints,
        )
        bm25_ms = round((perf_counter() - bm25_started) * 1000, 2)

        semantic_started = perf_counter()
        semantic_candidates = self._semantic_retrieve(
            db,
            variants=variants,
            user_role=user_role,
            candidate_limit=candidate_limit,
            source_type_hints=source_type_hints,
            document_hints=document_hints,
            accessible_chunks=accessible_chunks,
        )
        semantic_ms = round((perf_counter() - semantic_started) * 1000, 2)

        rrf_started = perf_counter()
        merged = self._merge_candidates_rrf(bm25_candidates, semantic_candidates)
        rrf_ms = round((perf_counter() - rrf_started) * 1000, 2)

        rerank_started = perf_counter()
        if task_mode == "procurement_fit_review":
            reranked = self._select_procurement_rrf_chunks(merged, bm25_candidates=bm25_candidates, top_k=top_k)
            rerank_debug = {
                "rerank_strategy": "bm25_anchor_rrf_for_procurement",
                "rerank_input_count": len(merged),
                "rerank_output_count": len(reranked),
                "query_variants": variants,
                "document_hints": document_hints,
                "cross_encoder_enabled": False,
                "cross_encoder_model": self.reranker.model_name,
                "cross_encoder_active": False,
                "cross_encoder_reason": "procurement_lightweight_path",
            }
        elif task_mode == "legal_contract_review":
            legal_shortlist = self._select_legal_rrf_chunks(
                merged,
                bm25_candidates=bm25_candidates,
                query_variants=variants,
                top_k=max(top_k * 3, 12),
            )
            reranked, rerank_debug = self.reranker.rerank(
                query=query,
                task_mode=task_mode,
                query_variants=variants,
                candidates=legal_shortlist,
                top_k=top_k,
                document_hints=document_hints,
            )
            rerank_debug["legal_shortlist_count"] = len(legal_shortlist)
            rerank_debug["legal_focus_terms"] = self._extract_legal_focus_terms(" ".join(variants))
        else:
            reranked, rerank_debug = self.reranker.rerank(
                query=query,
                task_mode=task_mode,
                query_variants=variants,
                candidates=merged,
                top_k=top_k,
                document_hints=document_hints,
            )
        rerank_ms = round((perf_counter() - rerank_started) * 1000, 2)

        debug = {
            "original_query": query,
            "rewritten_query": variants[1] if len(variants) > 1 else query,
            "query_variants": variants,
            "document_hints": document_hints,
            "domain_labels": domain_labels,
            "accessible_chunk_count": len(accessible_chunks),
            "bm25_candidate_count": len(bm25_candidates),
            "semantic_candidate_count": len(semantic_candidates),
            "rrf_merged_candidate_count": len(merged),
            "keyword_candidate_count": len(bm25_candidates),
            "vector_candidate_count": len(semantic_candidates),
            "merged_candidate_count": len(merged),
            "selected_titles": list(dict.fromkeys(chunk.document_title for chunk in reranked)),
            "selected_source_types": list(dict.fromkeys(chunk.source_type for chunk in reranked)),
            **rerank_debug,
        }
        debug["latency_ms"] = {
            "rewrite_ms": rewrite_ms,
            "load_chunks_ms": load_chunks_ms,
            "bm25_ms": bm25_ms,
            "semantic_ms": semantic_ms,
            "rrf_ms": rrf_ms,
            "rerank_ms": rerank_ms,
            "total_ms": round((perf_counter() - total_started) * 1000, 2),
        }
        debug["cache"] = {
            "enabled": True,
            "hit": False,
            "source": self._active_cache_backend_name(),
            "ttl_seconds": self.retrieval_cache_ttl_seconds,
            **self.cache_stats(),
        }
        self._store_cached_retrieval(cache_key, reranked, debug)
        return reranked, debug

    def _select_legal_rrf_chunks(
        self,
        merged: list[RetrievedChunk],
        *,
        bm25_candidates: list[RetrievedChunk],
        query_variants: list[str],
        top_k: int,
    ) -> list[RetrievedChunk]:
        if not merged:
            return []

        bm25_anchor_ids = {chunk.chunk_id for chunk in bm25_candidates[: max(top_k, 4)]}
        focus_terms = self._extract_legal_focus_terms(" ".join(query_variants))
        rescored: list[RetrievedChunk] = []
        for chunk in merged:
            heading_text = f"{chunk.document_title} {chunk.heading}".lower()
            content_text = chunk.content.lower()
            score = float(chunk.score)
            if chunk.chunk_id in bm25_anchor_ids:
                score += 0.08
            if any(term.lower() in heading_text or term.lower() in content_text for term in focus_terms):
                score += 0.12
            if any(keyword in heading_text for keyword in ("法务", "合同", "红线", "模板", "协议", "清单")):
                score += 0.04
            rescored.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    document_title=chunk.document_title,
                    source_type=chunk.source_type,
                    location=chunk.location,
                    content=chunk.content,
                    heading=chunk.heading,
                    score=round(score, 6),
                    score_breakdown={
                        **chunk.score_breakdown,
                        "legal_shortlist_bonus": round(score - float(chunk.score), 6),
                    },
                )
            )

        rescored.sort(key=lambda item: item.score, reverse=True)
        return _select_top_chunks(rescored, top_k=top_k)

    def _load_accessible_chunks(self, db: Session, *, user_role: str) -> list[ChunkRecord]:
        records: list[ChunkRecord] = []
        for chunk, document in self.repository.fetch_chunks(db):
            if not can_access(user_role, document.allowed_roles.split(",")):
                continue
            searchable_text = f"{document.title} {chunk.heading} {chunk.content} {chunk.keywords} {document.tags}"
            records.append(
                ChunkRecord(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_title=document.title,
                    document_tags=document.tags or "",
                    source_type=document.source_type,
                    location=chunk.location,
                    content=chunk.content,
                    heading=chunk.heading,
                    searchable_text=searchable_text,
                    tokens=tokenize_text(searchable_text),
                )
            )
        return records

    @staticmethod
    def _filter_accessible_chunks_for_task(
        records: list[ChunkRecord],
        *,
        task_mode: str,
        document_hints: list[str],
    ) -> list[ChunkRecord]:
        if task_mode != "legal_contract_review":
            return records

        filtered: list[ChunkRecord] = []
        for record in records:
            tags_lower = (record.document_tags or "").lower()
            title_lower = record.document_title.lower()
            searchable_lower = record.searchable_text.lower()

            if "project_artifact" in tags_lower or "legal_contract" in tags_lower:
                continue

            is_legal_kb = (
                record.document_title.startswith("法务核心-")
                or "baseline" in tags_lower
                or "legal" in tags_lower
                or any(hint.lower() in title_lower for hint in document_hints)
                or any(hint.lower() in searchable_lower for hint in document_hints)
            )
            if is_legal_kb:
                filtered.append(record)

        return filtered or [
            record
            for record in records
            if "project_artifact" not in (record.document_tags or "").lower()
            and "legal_contract" not in (record.document_tags or "").lower()
        ]

    def _bm25_retrieve(
        self,
        *,
        variants: list[str],
        records: list[ChunkRecord],
        candidate_limit: int,
        source_type_hints: list[str],
        document_hints: list[str],
    ) -> list[RetrievedChunk]:
        if not records:
            return []

        doc_freq: Counter[str] = Counter()
        for record in records:
            for token in set(record.tokens):
                doc_freq[token] += 1

        corpus_size = len(records)
        average_length = max(sum(len(record.tokens) for record in records) / corpus_size, 1.0)
        variant_tokens = [tokenize_text(item) for item in variants if item.strip()]
        candidates: list[RetrievedChunk] = []

        for record in records:
            term_freq = Counter(record.tokens)
            document_length = max(len(record.tokens), 1)
            best_bm25 = 0.0
            for query_tokens in variant_tokens:
                if not query_tokens:
                    continue
                score = 0.0
                for token in set(query_tokens):
                    frequency = term_freq.get(token, 0)
                    if frequency <= 0:
                        continue
                    df = doc_freq.get(token, 0)
                    idf = math.log(1.0 + (corpus_size - df + 0.5) / (df + 0.5))
                    numerator = frequency * (self.bm25_k1 + 1.0)
                    denominator = frequency + self.bm25_k1 * (
                        1.0 - self.bm25_b + self.bm25_b * document_length / average_length
                    )
                    score += idf * numerator / max(denominator, 1e-9)
                best_bm25 = max(best_bm25, score)

            if best_bm25 <= 0:
                continue

            source_bonus = 0.08 if record.source_type in source_type_hints else 0.0
            document_bonus = (
                0.08 if any(hint.lower() in record.searchable_text.lower() for hint in document_hints) else 0.0
            )
            total_score = round(best_bm25 + source_bonus + document_bonus, 4)
            candidates.append(
                RetrievedChunk(
                    chunk_id=record.chunk_id,
                    document_id=record.document_id,
                    document_title=record.document_title,
                    source_type=record.source_type,
                    location=record.location,
                    content=record.content,
                    heading=record.heading,
                    score=total_score,
                    score_breakdown={
                        "bm25": round(best_bm25, 4),
                        "semantic": 0.0,
                        "source_hint": round(source_bonus, 4),
                        "document_hint": round(document_bonus, 4),
                        "rrf": 0.0,
                        "fusion": total_score,
                    },
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:candidate_limit]

    def _semantic_retrieve(
        self,
        db: Session,
        *,
        variants: list[str],
        user_role: str,
        candidate_limit: int,
        source_type_hints: list[str],
        document_hints: list[str],
        accessible_chunks: list[ChunkRecord],
    ) -> list[RetrievedChunk]:
        if self.repository.is_pgvector_enabled(db):
            return self._semantic_retrieve_with_pgvector(
                db,
                variants=variants,
                user_role=user_role,
                candidate_limit=candidate_limit,
                source_type_hints=source_type_hints,
                document_hints=document_hints,
                accessible_chunks=accessible_chunks,
            )

        embeddings = [self.embedding_service.embed_text(item) for item in variants if item.strip()]
        candidates: list[RetrievedChunk] = []
        for record in accessible_chunks:
            cache_key = f"{record.chunk_id}:{self.embedding_service.model_name}:{self.embedding_service.device}"
            embedding_cache = getattr(self, "_local_embedding_cache", {})
            chunk_embedding = embedding_cache.get(cache_key)
            if chunk_embedding is None:
                chunk_embedding = self.embedding_service.embed_text(record.searchable_text)
                embedding_cache[cache_key] = chunk_embedding
                self._local_embedding_cache = embedding_cache
            best_similarity = 0.0
            for query_embedding in embeddings:
                best_similarity = max(
                    best_similarity,
                    self.embedding_service.cosine_similarity(query_embedding, chunk_embedding),
                )
            if best_similarity <= 0:
                continue

            source_bonus = 0.05 if record.source_type in source_type_hints else 0.0
            document_bonus = (
                0.05 if any(hint.lower() in record.searchable_text.lower() for hint in document_hints) else 0.0
            )
            total_score = round(best_similarity + source_bonus + document_bonus, 4)
            candidates.append(
                RetrievedChunk(
                    chunk_id=record.chunk_id,
                    document_id=record.document_id,
                    document_title=record.document_title,
                    source_type=record.source_type,
                    location=record.location,
                    content=record.content,
                    heading=record.heading,
                    score=total_score,
                    score_breakdown={
                        "bm25": 0.0,
                        "semantic": round(best_similarity, 4),
                        "source_hint": round(source_bonus, 4),
                        "document_hint": round(document_bonus, 4),
                        "rrf": 0.0,
                        "fusion": total_score,
                    },
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:candidate_limit]

    def _semantic_retrieve_with_pgvector(
        self,
        db: Session,
        *,
        variants: list[str],
        user_role: str,
        candidate_limit: int,
        source_type_hints: list[str],
        document_hints: list[str],
        accessible_chunks: list[ChunkRecord],
    ) -> list[RetrievedChunk]:
        candidates_by_id: dict[str, RetrievedChunk] = {}
        allowed_document_ids = list(dict.fromkeys(record.document_id for record in accessible_chunks))
        for variant in variants:
            query_embedding = self.embedding_service.embed_text(variant)
            for row in self.repository.fetch_vector_candidates(
                db,
                embedding=query_embedding,
                user_role=user_role,
                candidate_limit=max(candidate_limit * 4, 24),
                allowed_document_ids=allowed_document_ids,
            ):
                searchable_text = f"{row['document_title']} {row['heading']} {row['content']}"
                source_bonus = 0.05 if row["source_type"] in source_type_hints else 0.0
                document_bonus = 0.05 if any(hint.lower() in searchable_text.lower() for hint in document_hints) else 0.0
                semantic_score = max(float(row["vector_score"]), 0.0)
                total_score = round(semantic_score + source_bonus + document_bonus, 4)
                existing = candidates_by_id.get(str(row["chunk_id"]))
                if existing is None or total_score > existing.score:
                    candidates_by_id[str(row["chunk_id"])] = RetrievedChunk(
                        chunk_id=str(row["chunk_id"]),
                        document_id=str(row["document_id"]),
                        document_title=str(row["document_title"]),
                        source_type=str(row["source_type"]),
                        location=str(row["location"]),
                        content=str(row["content"]),
                        heading=str(row["heading"]),
                        score=total_score,
                        score_breakdown={
                            "bm25": 0.0,
                            "semantic": round(semantic_score, 4),
                            "source_hint": round(source_bonus, 4),
                            "document_hint": round(document_bonus, 4),
                            "rrf": 0.0,
                            "fusion": total_score,
                        },
                    )

        candidates = list(candidates_by_id.values())
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:candidate_limit]

    def _merge_candidates_rrf(
        self,
        bm25_candidates: list[RetrievedChunk],
        semantic_candidates: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        merged: dict[str, RetrievedChunk] = {}
        for ranked_list, label in ((bm25_candidates, "bm25"), (semantic_candidates, "semantic")):
            for rank, chunk in enumerate(ranked_list, start=1):
                weight = self.rrf_weights.get(label, 1.0)
                rrf_score = round(weight / (self.rrf_k + rank), 6)
                existing = merged.get(chunk.chunk_id)
                if existing is None:
                    chunk.score = rrf_score
                    chunk.score_breakdown["rrf"] = rrf_score
                    chunk.score_breakdown["fusion"] = rrf_score
                    merged[chunk.chunk_id] = chunk
                    continue

                existing.score = round(existing.score + rrf_score, 6)
                existing.score_breakdown[label] = max(
                    existing.score_breakdown.get(label, 0.0),
                    chunk.score_breakdown.get(label, 0.0),
                )
                existing.score_breakdown["source_hint"] = max(
                    existing.score_breakdown.get("source_hint", 0.0),
                    chunk.score_breakdown.get("source_hint", 0.0),
                )
                existing.score_breakdown["document_hint"] = max(
                    existing.score_breakdown.get("document_hint", 0.0),
                    chunk.score_breakdown.get("document_hint", 0.0),
                )
                existing.score_breakdown["rrf"] = round(existing.score_breakdown.get("rrf", 0.0) + rrf_score, 6)
                existing.score_breakdown["fusion"] = existing.score

        merged_candidates = list(merged.values())
        merged_candidates.sort(key=lambda item: item.score, reverse=True)
        return merged_candidates

    def _select_procurement_rrf_chunks(
        self,
        merged_candidates: list[RetrievedChunk],
        *,
        bm25_candidates: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        if not merged_candidates:
            return []
        if not bm25_candidates:
            return _select_top_chunks(merged_candidates, top_k=top_k)

        anchor_count = min(2, top_k, len(bm25_candidates))
        anchored = _select_top_chunks(bm25_candidates, top_k=anchor_count)
        if len(anchored) >= top_k:
            return anchored[:top_k]
        anchored_ids = {chunk.chunk_id for chunk in anchored}
        anchored_titles = {chunk.document_title for chunk in anchored}
        remaining = [
            chunk
            for chunk in merged_candidates
            if chunk.chunk_id not in anchored_ids and chunk.document_title not in anchored_titles
        ]
        return anchored + _select_top_chunks(remaining, top_k=top_k - len(anchored))

    def cache_stats(self) -> dict[str, object]:
        redis_stats = self.cache_backend.stats() if self.cache_backend else {}
        return {
            "backend": self._active_cache_backend_name(),
            "memory_size": len(self._retrieval_cache),
            "memory_hits": self._retrieval_cache_hits,
            "memory_misses": self._retrieval_cache_misses,
            "redis": redis_stats,
        }

    def _build_retrieval_cache_key(
        self,
        *,
        query: str,
        user_role: str,
        top_k: int,
        task_mode: str,
        query_variants: list[str],
        source_type_hints: list[str],
        document_hints: list[str],
        domain_labels: list[str],
    ) -> str:
        payload = {
            "query": query.strip(),
            "user_role": user_role,
            "top_k": top_k,
            "task_mode": task_mode,
            "query_variants": query_variants,
            "source_type_hints": source_type_hints,
            "document_hints": document_hints,
            "domain_labels": domain_labels,
            "reranker_model": self.reranker.model_name,
            "embedding_model": self.embedding_service.model_name,
            "embedding_device": self.embedding_service.device,
        }
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(serialized.encode("utf-8")).hexdigest()

    def _get_cached_retrieval(
        self,
        cache_key: str,
    ) -> tuple[tuple[list[RetrievedChunk], dict[str, object]] | None, str]:
        if self.cache_backend and self.cache_backend.available:
            cached_payload = self.cache_backend.get_json(cache_key)
            if cached_payload is not None:
                chunks = self._deserialize_cached_chunks(cached_payload.get("chunks", []))
                debug = copy.deepcopy(dict(cached_payload.get("debug", {})))
                self._store_memory_cached_retrieval(cache_key, chunks, debug)
                return (chunks, debug), "redis"

        cached = self._retrieval_cache.get(cache_key)
        if cached is None:
            self._retrieval_cache_misses += 1
            return None, self._active_cache_backend_name()

        cached_at, chunks, debug = cached
        if perf_counter() - cached_at > self.retrieval_cache_ttl_seconds:
            self._retrieval_cache.pop(cache_key, None)
            self._retrieval_cache_misses += 1
            return None, self._active_cache_backend_name()

        self._retrieval_cache.move_to_end(cache_key)
        self._retrieval_cache_hits += 1
        return (copy.deepcopy(chunks), copy.deepcopy(debug)), "memory"

    def _store_cached_retrieval(
        self,
        cache_key: str,
        chunks: list[RetrievedChunk],
        debug: dict[str, object],
    ) -> None:
        self._store_memory_cached_retrieval(cache_key, chunks, debug)
        if self.cache_backend and self.cache_backend.available:
            payload = {
                "chunks": self._serialize_cached_chunks(chunks),
                "debug": self._prune_cached_debug(debug),
            }
            self.cache_backend.set_json(cache_key, payload, self.retrieval_cache_ttl_seconds)

    def _store_memory_cached_retrieval(
        self,
        cache_key: str,
        chunks: list[RetrievedChunk],
        debug: dict[str, object],
    ) -> None:
        cached_debug = self._prune_cached_debug(debug)
        self._retrieval_cache[cache_key] = (perf_counter(), copy.deepcopy(chunks), cached_debug)
        self._retrieval_cache.move_to_end(cache_key)
        while len(self._retrieval_cache) > self.retrieval_cache_max_entries:
            self._retrieval_cache.popitem(last=False)

    @staticmethod
    def _serialize_cached_chunks(chunks: list[RetrievedChunk]) -> list[dict[str, object]]:
        return [
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "document_title": chunk.document_title,
                "source_type": chunk.source_type,
                "location": chunk.location,
                "content": chunk.content,
                "heading": chunk.heading,
                "score": chunk.score,
                "score_breakdown": chunk.score_breakdown,
            }
            for chunk in chunks
        ]

    @staticmethod
    def _deserialize_cached_chunks(items: object) -> list[RetrievedChunk]:
        if not isinstance(items, list):
            return []
        results: list[RetrievedChunk] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            results.append(
                RetrievedChunk(
                    chunk_id=str(item.get("chunk_id", "")),
                    document_id=str(item.get("document_id", "")),
                    document_title=str(item.get("document_title", "")),
                    source_type=str(item.get("source_type", "")),
                    location=str(item.get("location", "")),
                    content=str(item.get("content", "")),
                    heading=str(item.get("heading", "")),
                    score=float(item.get("score", 0.0)),
                    score_breakdown=dict(item.get("score_breakdown", {})),
                )
            )
        return results

    @staticmethod
    def _prune_cached_debug(debug: dict[str, object]) -> dict[str, object]:
        cached_debug = copy.deepcopy(debug)
        cached_debug.pop("latency_ms", None)
        cached_debug.pop("cache", None)
        return cached_debug

    def _active_cache_backend_name(self) -> str:
        if self.cache_backend and self.cache_backend.available:
            return "redis"
        return "memory"

    def fetch_document_sections(self, db: Session, document_ids: list[str]) -> list[RetrievedChunk]:
        sections: list[RetrievedChunk] = []
        documents = {document.id: document for document in self.repository.get_documents(db, document_ids)}
        if not documents:
            return sections
        for chunk, document in self.repository.fetch_chunks(db):
            if document.id not in documents:
                continue
            sections.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_title=document.title,
                    source_type=document.source_type,
                    location=chunk.location,
                    content=chunk.content,
                    heading=chunk.heading,
                    score=0.0,
                    score_breakdown={},
                )
            )
        return sections

    def compare_evidence(self, chunks: list[RetrievedChunk]) -> dict[str, object]:
        document_passages: dict[str, list[str]] = {}
        detected_clauses: dict[str, dict[str, str]] = {clause: {} for clause in CLAUSE_PATTERNS}

        for chunk in chunks:
            document_passages.setdefault(chunk.document_title, []).append(chunk.content[:180])
            searchable = f"{chunk.document_title} {chunk.heading} {chunk.content}".lower()
            for clause_name, patterns in CLAUSE_PATTERNS.items():
                if any(pattern.lower() in searchable for pattern in patterns):
                    current = detected_clauses[clause_name].get(chunk.document_title)
                    detected_clauses[clause_name][chunk.document_title] = current or "present"

        documents = list(document_passages.keys())
        clause_matrix: dict[str, dict[str, str]] = {}
        for clause_name, statuses in detected_clauses.items():
            if statuses:
                clause_matrix[clause_name] = {document: statuses.get(document, "missing") for document in documents}

        missing_clauses: dict[str, list[str]] = {document: [] for document in documents}
        for clause_name, statuses in clause_matrix.items():
            if any(status == "present" for status in statuses.values()):
                for document, status in statuses.items():
                    if status == "missing":
                        missing_clauses[document].append(clause_name)

        risk_flags: list[str] = []
        for document, missing in missing_clauses.items():
            if any(clause in missing for clause in ["责任上限", "赔偿责任", "数据处理", "审计权"]):
                risk_flags.append(f"{document} 缺少核心法务红线条款，请升级法务复核。")
            if "安全事件通知" in missing:
                risk_flags.append(f"{document} 未明确安全事件通知义务，需要同步信息安全团队评估。")

        return {
            "documents": document_passages,
            "clause_matrix": clause_matrix,
            "missing_clauses": {doc: clauses for doc, clauses in missing_clauses.items() if clauses},
            "risk_flags": risk_flags,
        }

    def compress_context(self, chunks: list[RetrievedChunk], char_budget: int = 2400) -> str:
        parts: list[str] = []
        consumed = 0
        for chunk in chunks:
            block = f"[{chunk.document_title} | {chunk.location}]\n{chunk.content.strip()}"
            if consumed + len(block) > char_budget:
                break
            parts.append(block)
            consumed += len(block)
        return "\n\n".join(parts)

    @staticmethod
    def to_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
        return [
            Citation(
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                location=chunk.location,
                snippet=chunk.content[:220],
                score=round(chunk.score, 4),
                score_breakdown=chunk.score_breakdown,
            )
            for chunk in chunks
        ]

    @staticmethod
    def _dedupe_fragments(fragments: list[str]) -> list[str]:
        results: list[str] = []
        seen: set[str] = set()
        for fragment in fragments:
            cleaned = fragment.strip().strip(",;，；")
            if len(cleaned) < 2:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            results.append(cleaned)
        return results

    @staticmethod
    def _rewrite_structured_procurement_query(query: str) -> str:
        if "采购场景" not in query or "检索重点" not in query:
            return ""

        priority_keys = (
            "项目名称",
            "项目摘要",
            "服务类型",
            "产品/服务简介",
            "风险信号",
            "缺失材料",
            "采购额外关注点",
            "检索重点",
        )
        section = ""
        fragments: list[str] = []
        for raw_line in query.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.endswith("：") and not line.startswith("-"):
                section = line[:-1]
                continue
            if not line.startswith("-"):
                continue

            item = line[1:].strip()
            parts = re.split(r"[:：]\s*", item, maxsplit=1)
            if len(parts) == 2:
                key, value = parts[0].strip(), parts[1].strip()
            else:
                key, value = section, item
            if not value or value in {"未提供", "未识别", "none", "unknown"}:
                continue
            if key in priority_keys or section in priority_keys:
                fragments.append(value)

        deduped = RetrievalService._dedupe_fragments(fragments)
        return " ".join(deduped[:14])[:420].strip()

    @staticmethod
    def _rewrite_structured_legal_query(query: str) -> str:
        if "法务合同红线审查" not in query and "差异摘要=" not in query and "差异描述=" not in query:
            return ""

        fragments: list[str] = []
        for raw_line in query.splitlines():
            line = raw_line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not value or key in {"项目", "供应商", "输出要求"}:
                continue
            if key == "业务场景":
                fragments.extend(part.strip() for part in re.split(r"[；;|]", value) if part.strip())
            if key == "差异描述":
                fragments.extend(part.strip() for part in re.split(r"[；;|]", value) if part.strip())
            elif key == "差异摘要":
                fragments.extend(part.strip() for part in re.split(r"[；;|]", value) if part.strip())
            elif key == "检索主题":
                fragments.extend(part.strip() for part in re.split(r"[、,，;；|]", value) if part.strip())
            elif key == "审查关注":
                fragments.extend(part.strip() for part in re.split(r"[、,，;；|]", value) if part.strip())
            elif key == "合同片段":
                fragments.extend(part.strip() for part in value.split("|") if part.strip())
        deduped = RetrievalService._dedupe_fragments(fragments)
        return " ".join(deduped[:8])[:280].strip()

    @staticmethod
    def _extract_legal_focus_terms(text: str) -> list[str]:
        terms: list[str] = []
        for term in (
            "责任上限",
            "赔偿责任",
            "审计权",
            "数据处理",
            "保密义务",
            "安全事件通知",
            "分包限制",
            "便利终止",
            "付款条款",
            "服务水平",
            "争议解决与适用法律",
            "合同审查红线",
            "标准主服务协议",
            "供应商回传红线",
            "数据处理检查清单",
        ):
            if term in text:
                terms.append(term)
        return terms

    @staticmethod
    def _extract_query_fragments(normalized: str) -> list[str]:
        working_text = normalized.replace("。", "\n").replace("；", "\n")
        coarse_lines = re.split(r"[\n\r]+|\s+-\s+", working_text)
        fragments: list[str] = []
        for raw_line in coarse_lines:
            line = re.sub(r"^[\-\*\u2022]+\s*", "", raw_line.strip())
            if not line:
                continue

            lowered = line.lower()
            if any(lowered.startswith(prefix) for prefix in INSTRUCTION_PREFIXES):
                continue

            parts = re.split(r"[:：]\s*", line, maxsplit=1)
            if len(parts) == 2:
                key, value = parts[0].strip(), parts[1].strip()
                if value and len(value) > 2:
                    fragments.append(value)
                    continue
                if key and len(key) > 2:
                    fragments.append(key)
                    continue

            fragments.append(line)
        return fragments
