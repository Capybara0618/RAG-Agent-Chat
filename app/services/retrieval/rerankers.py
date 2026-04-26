from __future__ import annotations

from pathlib import Path
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.retrieval.service import RetrievedChunk


def _select_top_chunks(
    candidates: list["RetrievedChunk"],
    *,
    top_k: int,
) -> list["RetrievedChunk"]:
    selected: list["RetrievedChunk"] = []
    seen_documents: set[str] = set()
    seen_fingerprints: set[str] = set()

    # First pass: prefer document diversity so one file does not flood top-k.
    for chunk in candidates:
        fingerprint = f"{chunk.document_title}:{chunk.content[:120]}"
        if fingerprint in seen_fingerprints or chunk.document_title in seen_documents:
            continue
        seen_fingerprints.add(fingerprint)
        seen_documents.add(chunk.document_title)
        selected.append(chunk)
        if len(selected) >= top_k:
            return selected

    # Second pass: fill remaining slots with the next best unique chunks.
    for chunk in candidates:
        fingerprint = f"{chunk.document_title}:{chunk.content[:120]}"
        if fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(fingerprint)
        selected.append(chunk)
        if len(selected) >= top_k:
            break

    return selected


class HeuristicReranker:
    def rerank(
        self,
        *,
        query: str,
        task_mode: str,
        query_variants: list[str],
        candidates: list["RetrievedChunk"],
        top_k: int,
        document_hints: list[str],
    ) -> tuple[list["RetrievedChunk"], dict[str, object]]:
        preferred_labels = {
            "legal_contract_review": ("template", "playbook", "redline", "条款", "法务", "合同"),
            "procurement_fit_review": ("faq", "policy", "guide", "matrix", "审批", "安全", "供应商"),
            "knowledge_qa": (),
        }
        favored = preferred_labels.get(task_mode, ())
        reranked: list["RetrievedChunk"] = []

        for chunk in candidates:
            chunk = replace(chunk)
            heading_text = f"{chunk.document_title} {chunk.heading}".lower()
            preference_bonus = 0.04 if any(label in heading_text for label in favored) else 0.0
            hint_bonus = 0.03 if any(hint.lower() in heading_text for hint in document_hints) else 0.0
            rerank_bonus = round(preference_bonus + hint_bonus, 4)
            chunk.score = round(chunk.score + rerank_bonus, 4)
            chunk.score_breakdown["rerank_bonus"] = rerank_bonus
            reranked.append(chunk)

        reranked.sort(key=lambda item: item.score, reverse=True)
        selected = _select_top_chunks(reranked, top_k=top_k)

        return selected, {
            "rerank_strategy": "heuristic",
            "rerank_input_count": len(candidates),
            "rerank_output_count": len(selected),
            "query_variants": query_variants,
            "document_hints": document_hints,
        }


class CrossEncoderReranker:
    _MODEL_CACHE: dict[tuple[str, str], object] = {}

    def __init__(self, *, model_name: str, device: str = "cpu", enabled: bool = True) -> None:
        self.model_name = model_name
        self.device = device
        self.enabled = enabled
        self._model = None
        self._load_error = ""

    def rerank(
        self,
        *,
        query: str,
        task_mode: str,
        query_variants: list[str],
        candidates: list["RetrievedChunk"],
        top_k: int,
        document_hints: list[str],
    ) -> tuple[list["RetrievedChunk"], dict[str, object]]:
        if not candidates:
            return [], {
                "rerank_strategy": "cross_encoder",
                "rerank_input_count": 0,
                "rerank_output_count": 0,
                "cross_encoder_enabled": self.enabled,
                "cross_encoder_model": self.model_name,
                "cross_encoder_active": False,
                "cross_encoder_reason": "no_candidates",
            }

        model = self._load_model()
        if model is None:
            selected = _select_top_chunks(candidates, top_k=top_k)
            debug = {
                "rerank_strategy": "passthrough",
                "rerank_input_count": len(candidates),
                "rerank_output_count": len(selected),
                "query_variants": query_variants,
                "document_hints": document_hints,
                "cross_encoder_enabled": self.enabled,
                "cross_encoder_model": self.model_name,
                "cross_encoder_active": False,
                "cross_encoder_reason": self._load_error or "unavailable",
            }
            return selected, debug

        rerank_query = self._build_rerank_query(query=query, query_variants=query_variants)
        pairs = [(rerank_query, self._build_pair_text(chunk)) for chunk in candidates]
        try:
            raw_scores = list(model.predict(pairs, show_progress_bar=False))
        except Exception as exc:
            self._load_error = str(exc)
            selected = _select_top_chunks(candidates, top_k=top_k)
            debug = {
                "rerank_strategy": "passthrough",
                "rerank_input_count": len(candidates),
                "rerank_output_count": len(selected),
                "query_variants": query_variants,
                "document_hints": document_hints,
                "cross_encoder_enabled": self.enabled,
                "cross_encoder_model": self.model_name,
                "cross_encoder_active": False,
                "cross_encoder_reason": self._load_error,
            }
            return selected, debug

        retrieval_scores = [float(chunk.score) for chunk in candidates]
        min_retrieval = min(retrieval_scores) if retrieval_scores else 0.0
        max_retrieval = max(retrieval_scores) if retrieval_scores else 0.0

        reranked: list["RetrievedChunk"] = []
        retrieval_prior_weight = 0.18 if task_mode == "legal_contract_review" else 0.35
        for chunk, raw_score in zip(candidates, raw_scores):
            chunk = replace(chunk)
            ce_score = float(raw_score)
            retrieval_prior = self._normalize_score(
                float(chunk.score),
                minimum=min_retrieval,
                maximum=max_retrieval,
            )
            hint_bonus = 0.02 if any(hint.lower() in f"{chunk.document_title} {chunk.heading}".lower() for hint in document_hints) else 0.0
            final_score = round(ce_score + retrieval_prior_weight * retrieval_prior + hint_bonus, 6)
            chunk.score = final_score
            chunk.score_breakdown["cross_encoder"] = round(ce_score, 6)
            chunk.score_breakdown["retrieval_prior"] = round(retrieval_prior, 6)
            chunk.score_breakdown["retrieval_prior_weight"] = round(retrieval_prior_weight, 6)
            chunk.score_breakdown["rerank_bonus"] = round(hint_bonus, 6)
            chunk.score_breakdown["fusion"] = final_score
            reranked.append(chunk)

        reranked.sort(key=lambda item: item.score, reverse=True)
        selected = _select_top_chunks(reranked, top_k=top_k)
        return selected, {
            "rerank_strategy": "cross_encoder",
            "rerank_input_count": len(candidates),
            "rerank_output_count": len(selected),
            "query_variants": query_variants,
            "document_hints": document_hints,
            "cross_encoder_enabled": self.enabled,
            "cross_encoder_model": self.model_name,
            "cross_encoder_active": True,
            "cross_encoder_reason": "",
            "rerank_query": rerank_query,
        }

    def _load_model(self):
        if not self.enabled:
            self._load_error = "disabled"
            return None
        if self._model is not None:
            return self._model
        cache_key = (self.model_name, self.device)
        cached = self._MODEL_CACHE.get(cache_key)
        if cached is not None:
            self._model = cached
            return self._model
        model_path = Path(self.model_name)
        local_files_only = not model_path.exists()
        try:
            from sentence_transformers import CrossEncoder
        except Exception as exc:
            self._load_error = f"sentence-transformers unavailable: {exc}"
            return None
        try:
            self._model = CrossEncoder(
                self.model_name,
                device=self.device,
                trust_remote_code=True,
                local_files_only=local_files_only,
            )
            self._MODEL_CACHE[cache_key] = self._model
        except Exception as exc:
            self._load_error = f"local_cross_encoder_unavailable: {exc}"
            self._model = None
        return self._model

    @staticmethod
    def _build_pair_text(chunk: "RetrievedChunk") -> str:
        body = chunk.content.strip()
        if len(body) > 1600:
            body = body[:1600]
        return f"{chunk.document_title}\n{chunk.heading}\n{body}".strip()

    @staticmethod
    def _build_rerank_query(*, query: str, query_variants: list[str]) -> str:
        normalized_parts: list[str] = []
        for item in [*query_variants, query]:
            text = " ".join(str(item).split())
            if not text:
                continue
            if len(text) > 420:
                text = text[:420]
            if text not in normalized_parts:
                normalized_parts.append(text)

        if not normalized_parts:
            return query

        preferred = [
            item
            for item in normalized_parts
            if 24 <= len(item) <= 260
        ]
        if preferred:
            primary = preferred[0]
            secondary = next((item for item in preferred[1:] if item != primary), "")
        else:
            primary = normalized_parts[0]
            secondary = next((item for item in normalized_parts[1:] if item != primary), "")

        selected = [primary]
        if secondary:
            selected.append(secondary)
        return "\n".join(selected[:2])

    @staticmethod
    def _normalize_score(value: float, *, minimum: float, maximum: float) -> float:
        if maximum <= minimum:
            return 0.0
        return (value - minimum) / (maximum - minimum)
