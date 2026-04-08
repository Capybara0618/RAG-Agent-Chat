from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.security import can_access
from app.repositories.document_repository import DocumentRepository
from app.schemas.common import Citation
from app.services.retrieval.embeddings import EmbeddingService, tokenize_text


CLAUSE_PATTERNS = {
    "责任上限": ("liability cap", "limitation of liability", "责任上限", "赔偿上限"),
    "赔偿条款": ("indemnity", "赔偿", "赔偿责任"),
    "审计权": ("audit right", "audit rights", "审计权", "审计访问"),
    "数据处理": ("data processing", "dpa", "个人信息", "数据处理", "数据出境"),
    "安全事件通知": ("security incident", "breach notice", "安全事件", "通知时限"),
    "分包限制": ("subcontractor", "sub-processor", "分包", "转包"),
    "便利终止": ("termination for convenience", "convenience termination", "便利终止", "无因终止"),
    "付款条款": ("payment terms", "invoice", "net 45", "付款条款", "发票"),
    "服务水平": ("sla", "service level", "service credit", "服务水平", "服务赔偿"),
}


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


class HybridReranker:
    def rerank(
        self,
        *,
        query: str,
        intent: str,
        query_variants: list[str],
        candidates: list[RetrievedChunk],
        top_k: int,
        document_hints: list[str],
    ) -> tuple[list[RetrievedChunk], dict[str, object]]:
        preferred_labels = {
            "compare": ("template", "playbook", "redline", "条款", "法务", "合同"),
            "workflow": ("sop", "runbook", "流程", "准入", "审批", "security"),
            "support": ("faq", "policy", "guide", "matrix", "清单", "准入"),
        }
        selected: list[RetrievedChunk] = []
        reranked: list[RetrievedChunk] = []
        seen_fingerprints: set[str] = set()
        favored = preferred_labels.get(intent, ())

        for chunk in candidates:
            heading_text = f"{chunk.document_title} {chunk.heading}".lower()
            preference_bonus = 0.08 if any(label in heading_text for label in favored) else 0.0
            hint_bonus = 0.06 if any(hint.lower() in heading_text for hint in document_hints) else 0.0
            diversity_bonus = 0.03 if chunk.document_title not in {item.document_title for item in selected} else 0.0
            chunk.score = round(chunk.score + preference_bonus + hint_bonus + diversity_bonus, 4)
            chunk.score_breakdown["rerank_bonus"] = round(preference_bonus + hint_bonus + diversity_bonus, 4)
            reranked.append(chunk)

        reranked.sort(key=lambda item: item.score, reverse=True)

        for chunk in reranked:
            fingerprint = f"{chunk.document_title}:{chunk.content[:120]}"
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)
            selected.append(chunk)
            if len(selected) >= top_k:
                break

        return selected, {
            "rerank_input_count": len(candidates),
            "rerank_output_count": len(selected),
            "query_variants": query_variants,
            "document_hints": document_hints,
        }


class RetrievalService:
    def __init__(self, repository: DocumentRepository, embedding_service: EmbeddingService) -> None:
        self.repository = repository
        self.embedding_service = embedding_service
        self.reranker = HybridReranker()

    def rewrite_query(self, query: str) -> str:
        normalized = " ".join(query.strip().split())
        synonyms = {
            "contract": "contract clause legal redline template obligation",
            "vendor": "vendor supplier onboarding due diligence security review",
            "msa": "master service agreement liability audit termination data processing",
            "nda": "confidentiality disclosure term return destruction",
            "security review": "security review questionnaire infosec assessment data handling",
            "approval": "approval matrix delegation of authority legal finance security",
            "采购": "采购 供应商 准入 合同 审批 尽调",
            "供应商": "供应商 准入 尽调 安全评审 财务资质",
            "合同": "合同 条款 红线 模板 审查 审批",
            "法务": "法务 审查 红线 责任上限 赔偿 审计权",
            "安全评审": "安全评审 问卷 数据处理 安全事件 通知",
            "审批矩阵": "审批矩阵 授权级别 法务 财务 采购",
        }
        expanded = normalized
        lowered = normalized.lower()
        for trigger, addition in synonyms.items():
            if trigger in lowered and addition not in lowered:
                expanded = f"{expanded} {addition}"
        return expanded.strip()

    def build_query_variants(self, query: str, plan: dict[str, object] | None = None) -> list[str]:
        variants = [query]
        rewritten = self.rewrite_query(query)
        if rewritten != query:
            variants.append(rewritten)

        if plan:
            for variant in plan.get("query_variants", []):
                variant_text = str(variant).strip()
                if variant_text and variant_text not in variants:
                    variants.append(variant_text)
        return variants

    def retrieve(
        self,
        db: Session,
        *,
        query: str,
        user_role: str,
        top_k: int,
        plan: dict[str, object] | None = None,
    ) -> tuple[list[RetrievedChunk], dict[str, object]]:
        variants = self.build_query_variants(query, plan)
        source_type_hints = [str(item) for item in (plan or {}).get("source_type_hints", [])]
        document_hints = [str(item) for item in (plan or {}).get("document_hints", [])]
        keyword_candidates = self._keyword_retrieve(
            db,
            variants=variants,
            user_role=user_role,
            candidate_limit=max(top_k * 6, 12),
            source_type_hints=source_type_hints,
            document_hints=document_hints,
        )
        vector_candidates = self._vector_retrieve(
            db,
            variants=variants,
            user_role=user_role,
            candidate_limit=max(top_k * 6, 12),
            source_type_hints=source_type_hints,
            document_hints=document_hints,
        )
        merged = self._merge_candidates(keyword_candidates, vector_candidates)
        reranked, rerank_debug = self.reranker.rerank(
            query=query,
            intent=str((plan or {}).get("intent", "qa")),
            query_variants=variants,
            candidates=merged,
            top_k=top_k,
            document_hints=document_hints,
        )
        return reranked, {
            "original_query": query,
            "rewritten_query": variants[1] if len(variants) > 1 else query,
            "query_variants": variants,
            "document_hints": document_hints,
            "domain_labels": list((plan or {}).get("domain_labels", [])),
            "keyword_candidate_count": len(keyword_candidates),
            "vector_candidate_count": len(vector_candidates),
            "merged_candidate_count": len(merged),
            **rerank_debug,
        }

    def _keyword_retrieve(
        self,
        db: Session,
        *,
        variants: list[str],
        user_role: str,
        candidate_limit: int,
        source_type_hints: list[str],
        document_hints: list[str],
    ) -> list[RetrievedChunk]:
        variant_tokens = [set(tokenize_text(item)) for item in variants]
        candidates: list[RetrievedChunk] = []
        for chunk, document in self.repository.fetch_chunks(db):
            if not can_access(user_role, document.allowed_roles.split(",")):
                continue
            searchable_text = f"{document.title} {chunk.heading} {chunk.content} {chunk.keywords} {document.tags}"
            chunk_tokens = set(tokenize_text(searchable_text))
            best_overlap = 0.0
            for tokens in variant_tokens:
                if not tokens:
                    continue
                best_overlap = max(best_overlap, len(tokens & chunk_tokens) / max(len(tokens), 1))
            if best_overlap <= 0:
                continue
            source_bonus = 0.08 if document.source_type in source_type_hints else 0.0
            document_bonus = 0.07 if any(hint.lower() in searchable_text.lower() for hint in document_hints) else 0.0
            candidates.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_title=document.title,
                    source_type=document.source_type,
                    location=chunk.location,
                    content=chunk.content,
                    heading=chunk.heading,
                    score=round(best_overlap + source_bonus + document_bonus, 4),
                    score_breakdown={
                        "keyword": round(best_overlap, 4),
                        "vector": 0.0,
                        "source_hint": round(source_bonus, 4),
                        "document_hint": round(document_bonus, 4),
                        "fusion": round(best_overlap + source_bonus + document_bonus, 4),
                    },
                )
            )
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:candidate_limit]

    def _vector_retrieve(
        self,
        db: Session,
        *,
        variants: list[str],
        user_role: str,
        candidate_limit: int,
        source_type_hints: list[str],
        document_hints: list[str],
    ) -> list[RetrievedChunk]:
        if self.repository.is_pgvector_enabled(db):
            return self._vector_retrieve_with_pgvector(
                db,
                variants=variants,
                user_role=user_role,
                candidate_limit=candidate_limit,
                source_type_hints=source_type_hints,
                document_hints=document_hints,
            )

        embeddings = [self.embedding_service.embed_text(item) for item in variants]
        candidates: list[RetrievedChunk] = []
        for chunk, document in self.repository.fetch_chunks(db):
            if not can_access(user_role, document.allowed_roles.split(",")):
                continue
            searchable_text = f"{document.title} {chunk.heading} {chunk.content} {chunk.keywords} {document.tags}"
            chunk_embedding = self.embedding_service.embed_text(chunk.content)
            best_similarity = 0.0
            for query_embedding in embeddings:
                best_similarity = max(best_similarity, self.embedding_service.cosine_similarity(query_embedding, chunk_embedding))
            if best_similarity <= 0:
                continue
            source_bonus = 0.05 if document.source_type in source_type_hints else 0.0
            document_bonus = 0.05 if any(hint.lower() in searchable_text.lower() for hint in document_hints) else 0.0
            candidates.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_title=document.title,
                    source_type=document.source_type,
                    location=chunk.location,
                    content=chunk.content,
                    heading=chunk.heading,
                    score=round(best_similarity + source_bonus + document_bonus, 4),
                    score_breakdown={
                        "keyword": 0.0,
                        "vector": round(best_similarity, 4),
                        "source_hint": round(source_bonus, 4),
                        "document_hint": round(document_bonus, 4),
                        "fusion": round(best_similarity + source_bonus + document_bonus, 4),
                    },
                )
            )
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:candidate_limit]

    def _vector_retrieve_with_pgvector(
        self,
        db: Session,
        *,
        variants: list[str],
        user_role: str,
        candidate_limit: int,
        source_type_hints: list[str],
        document_hints: list[str],
    ) -> list[RetrievedChunk]:
        candidates_by_id: dict[str, RetrievedChunk] = {}
        for variant in variants:
            query_embedding = self.embedding_service.embed_text(variant)
            for row in self.repository.fetch_vector_candidates(
                db,
                embedding=query_embedding,
                user_role=user_role,
                candidate_limit=candidate_limit,
            ):
                searchable_text = f"{row['document_title']} {row['heading']} {row['content']}"
                source_bonus = 0.05 if row["source_type"] in source_type_hints else 0.0
                document_bonus = 0.05 if any(hint.lower() in searchable_text.lower() for hint in document_hints) else 0.0
                vector_score = max(float(row["vector_score"]), 0.0)
                total_score = round(vector_score + source_bonus + document_bonus, 4)
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
                            "keyword": 0.0,
                            "vector": round(vector_score, 4),
                            "source_hint": round(source_bonus, 4),
                            "document_hint": round(document_bonus, 4),
                            "fusion": total_score,
                        },
                    )
        candidates = list(candidates_by_id.values())
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:candidate_limit]

    def _merge_candidates(self, keyword_candidates: list[RetrievedChunk], vector_candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        merged: dict[str, RetrievedChunk] = {}
        for ranked_list, label in ((keyword_candidates, "keyword"), (vector_candidates, "vector")):
            for rank, chunk in enumerate(ranked_list, start=1):
                fusion_score = round(1.0 / (rank + 10), 4)
                existing = merged.get(chunk.chunk_id)
                if existing is None:
                    chunk.score = fusion_score
                    chunk.score_breakdown["fusion"] = fusion_score
                    merged[chunk.chunk_id] = chunk
                    continue
                existing.score = round(existing.score + fusion_score, 4)
                existing.score_breakdown[label] = max(
                    existing.score_breakdown.get(label, 0.0),
                    chunk.score_breakdown.get(label, 0.0),
                )
                existing.score_breakdown["fusion"] = existing.score
                existing.score_breakdown["document_hint"] = max(
                    existing.score_breakdown.get("document_hint", 0.0),
                    chunk.score_breakdown.get("document_hint", 0.0),
                )
        merged_candidates = list(merged.values())
        merged_candidates.sort(key=lambda item: item.score, reverse=True)
        return merged_candidates

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
            if any(clause in missing for clause in ["责任上限", "赔偿条款", "数据处理", "审计权"]):
                risk_flags.append(f"{document} 缺少核心法务红线条款，请升级法务复核。")
            if "安全事件通知" in missing:
                risk_flags.append(f"{document} 未明确安全事件通知义务，需同步信息安全团队评估。")

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
            block = f"[{chunk.document_title} | {chunk.location}] {chunk.content}".strip()
            if consumed + len(block) > char_budget and parts:
                break
            parts.append(block)
            consumed += len(block)
        return "\n\n".join(parts)

    def to_citations(self, chunks: list[RetrievedChunk]) -> list[Citation]:
        return [
            Citation(
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                location=chunk.location,
                snippet=chunk.content[:240],
                score=chunk.score,
                score_breakdown=chunk.score_breakdown,
            )
            for chunk in chunks
        ]
