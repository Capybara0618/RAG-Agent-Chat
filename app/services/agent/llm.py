from __future__ import annotations

import json
import re

import httpx

from app.schemas.common import Citation
from app.services.agent.providers import LLMProvider
from app.services.retrieval.embeddings import tokenize_text
from app.services.retrieval.service import RetrievedChunk


SENTENCE_PATTERN = re.compile(r"(?<=[.!?。！？])\s*")


class LLMClient(LLMProvider):
    def __init__(self, *, api_base: str = "", api_key: str = "", model: str = "") -> None:
        self.api_base = api_base
        self.api_key = api_key
        self.model = model

    def build_retrieval_plan(self, query: str, task_mode: str, top_k: int) -> dict[str, object]:
        defaults = self._task_defaults(task_mode)
        query_variants = self._derive_query_variants(query=query, task_mode=task_mode)
        return {
            "task_mode": task_mode,
            "intent": task_mode,
            "top_k": top_k + (1 if task_mode == "legal_contract_review" else 0),
            "rerank_k": max(top_k * 3, 10),
            "allow_multi_doc": task_mode == "legal_contract_review",
            "query_variants": query_variants,
            "source_type_hints": defaults["source_type_hints"],
            "document_hints": defaults["document_hints"],
            "domain_labels": defaults["domain_labels"],
        }

    def _derive_query_variants(self, *, query: str, task_mode: str) -> list[str]:
        if task_mode == "legal_contract_review":
            return self._build_legal_query_variants(query)
        return []

    @staticmethod
    def _build_legal_query_variants(query: str) -> list[str]:
        normalized = " ".join(str(query).split())
        if not normalized:
            return []

        business_match = re.search(r"业务场景=([^\n]+)", query)
        business_terms = []
        if business_match:
            business_terms = [
                part.strip()
                for part in re.split(r"[；;|]", business_match.group(1))
                if part.strip()
            ]
        business_terms = list(dict.fromkeys(business_terms))[:4]

        concern_match = re.search(r"差异描述=([^\n]+)", query)
        concern_phrases = []
        if concern_match:
            concern_phrases = [
                part.strip()
                for part in re.split(r"[；;|]", concern_match.group(1))
                if part.strip()
            ]
        concern_phrases = list(dict.fromkeys(concern_phrases))[:4]

        summary_match = re.search(r"差异摘要=([^\n]+)", query)
        clause_tokens = []
        if summary_match:
            clause_tokens = re.findall(r"([^\s；;,=]+?)(?:缺失|弱化)", summary_match.group(1))
        clauses = [item.strip() for item in clause_tokens if item.strip()]
        clauses = list(dict.fromkeys(clauses))[:4]

        topic_match = re.search(r"检索主题=([^\n]+)", query)
        topics = []
        if topic_match:
            topics = [part.strip() for part in re.split(r"[、,，;；|]", topic_match.group(1)) if part.strip()]
        topics = list(dict.fromkeys(topics))[:6]

        variants: list[str] = []
        if business_terms and concern_phrases:
            variants.append(" ".join([*business_terms[:2], *concern_phrases[:2]]))
        elif business_terms:
            variants.append(" ".join(business_terms[:3]))
        if concern_phrases:
            variants.append(" ".join(concern_phrases[:2]))
        if concern_phrases and topics:
            variants.append(" ".join([*concern_phrases[:2], *topics[:2]]))
        if clauses and topics:
            variants.append(" ".join([*clauses[:2], *topics[:2]]))
        elif clauses:
            variants.append(" ".join(clauses[:3]))
        elif topics:
            variants.append(" ".join(topics[:3]))
        return list(dict.fromkeys(item[:180] for item in variants if item.strip()))

    def extract_supplier_profile(
        self,
        *,
        project_context: dict[str, str],
        combined_text: str,
        material_names: list[str],
    ) -> dict[str, object] | None:
        if not self.api_key:
            return None

        source_text = combined_text.strip()
        if not source_text:
            return None

        system_prompt = (
            "You extract supplier onboarding information for procurement review. "
            "Return only valid JSON. Do not add markdown fences."
        )
        user_prompt = (
            "Read the supplier materials and produce a structured summary for procurement review.\n"
            "Project context:\n"
            f"- title: {project_context.get('title', '')}\n"
            f"- category: {project_context.get('category', '')}\n"
            f"- data_scope: {project_context.get('data_scope', '')}\n"
            f"- department: {project_context.get('department', '')}\n"
            f"- material_names: {', '.join(material_names[:8])}\n\n"
            "Return a JSON object with these keys:\n"
            "vendor_name, company_summary, products_services, data_involvement, "
            "security_signals, compliance_signals, legal_signals, source_urls, missing_materials, "
            "recommended_focus, confidence.\n\n"
            "Supplier materials:\n"
            f"{source_text[:16000]}"
        )

        try:
            content = self._chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception:
            return None
        if not content:
            return None
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def compose_answer(
        self,
        *,
        query: str,
        task_mode: str,
        citations: list[Citation],
        retrieved_chunks: list[RetrievedChunk],
        comparison_view: dict[str, object] | None,
        history: list[dict[str, str]],
    ) -> tuple[str, float, str]:
        if self._is_out_of_scope_query(query):
            return (
                "当前系统定位为采购适配度审查和合同审查助手，只回答制度、条款、审批和评审流程问题，不替代人工做最终商业或法务决策。",
                0.08,
                "refuse",
            )

        if not citations:
            return (
                "当前知识库没有足够证据支持本次审查结论。请补充更具体的供应商信息、合同条款或制度范围后再试。",
                0.12,
                "clarify",
            )

        if task_mode == "legal_contract_review":
            return self._compose_legal_review_answer(query, comparison_view, retrieved_chunks)
        if task_mode == "procurement_fit_review":
            return self._compose_procurement_fit_answer(query, retrieved_chunks)
        return self._compose_qa_answer(retrieved_chunks, bool(history))

    def verify_citations(self, answer: str, citations: list[Citation]) -> tuple[float, str, dict[str, object]]:
        if not citations:
            return 0.1, "refuse", {"coverage_ratio": 0.0, "has_conflict": False}

        answer_tokens = set(tokenize_text(answer))
        evidence_tokens = set()
        document_titles = {citation.document_title for citation in citations}
        for citation in citations:
            evidence_tokens.update(tokenize_text(citation.snippet))

        overlap = len(answer_tokens & evidence_tokens) / max(len(answer_tokens), 1)
        has_conflict = self._has_conflict(citations)
        debug = {
            "coverage_ratio": round(overlap, 4),
            "citation_count": len(citations),
            "document_count": len(document_titles),
            "has_conflict": has_conflict,
        }
        if has_conflict:
            return 0.41, "clarify", debug
        if overlap < 0.18:
            return 0.36, "clarify", debug
        return min(0.92, 0.58 + overlap), "answer", debug

    def _chat_json(self, *, system_prompt: str, user_prompt: str) -> str:
        base_url = self.api_base.rstrip("/") if self.api_base else "https://api.openai.com/v1"
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model or "gpt-4.1-mini",
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return str(message.get("content") or "").strip()

    def _compose_legal_review_answer(
        self,
        query: str,
        comparison_view: dict[str, object] | None,
        retrieved_chunks: list[RetrievedChunk],
    ) -> tuple[str, float, str]:
        if comparison_view:
            clause_matrix = comparison_view.get("clause_matrix", {})
            missing_clauses = comparison_view.get("missing_clauses", {})
            risk_flags = comparison_view.get("risk_flags", [])
            lines = [f"合同审查结论：{query}"]

            if clause_matrix:
                lines.append("重点条款差异：")
                for clause_name, statuses in list(clause_matrix.items())[:4]:
                    formatted = "；".join(f"{doc}={status}" for doc, status in statuses.items())
                    lines.append(f"- {clause_name}：{formatted}")

            if missing_clauses:
                lines.append("缺失或弱化条款：")
                for doc_title, clauses in list(missing_clauses.items())[:2]:
                    if clauses:
                        lines.append(f"- {doc_title}：缺少 {', '.join(clauses[:4])}")

            if risk_flags:
                lines.append("风险提示：")
                for item in risk_flags[:3]:
                    lines.append(f"- {item}")

            lines.append("建议：若涉及责任上限、赔偿、审计权、数据处理或分包限制等核心红线，应升级法务复核。")
            return "\n".join(lines), 0.85, "answer"

        grouped: dict[str, list[RetrievedChunk]] = {}
        for chunk in retrieved_chunks:
            grouped.setdefault(chunk.document_title, []).append(chunk)
        if len(grouped) < 2:
            return (
                "当前命中的法务证据不足以完成可靠的合同对比，请补充标准模板或对方修改版合同。",
                0.44,
                "clarify",
            )

        lines = [f"合同条款对比：{query}"]
        for title, chunks in list(grouped.items())[:3]:
            lines.append(f"- {title}：{self._first_sentence(chunks[0].content)}")
        lines.append("建议继续按责任上限、赔偿、数据处理、审计权和终止条款逐项核对。")
        return "\n".join(lines), 0.79, "answer"

    def _compose_procurement_fit_answer(
        self,
        query: str,
        retrieved_chunks: list[RetrievedChunk],
    ) -> tuple[str, float, str]:
        chunk = retrieved_chunks[0]
        lines = [
            f"供应商匹配度审查：{query}",
            f"制度依据：{self._first_sentence(chunk.content)}",
            "判断维度：需求是否匹配、风险是否可控、材料是否齐备。",
            "建议：先按命中的准入制度和安全评审要求补齐材料；若涉及数据处理、关键风险或升级条件，再提交法务或安全复核。",
            "边界提示：本结论用于采购辅助判断，不替代采购、法务或管理层的最终人工决定。",
        ]
        return "\n".join(lines), 0.81, "answer"

    def _compose_qa_answer(self, retrieved_chunks: list[RetrievedChunk], has_history: bool) -> tuple[str, float, str]:
        primary = retrieved_chunks[0]
        answer = self._first_sentence(primary.content)
        if len(retrieved_chunks) > 1:
            answer = f"{answer} 另外，{retrieved_chunks[1].document_title} 中也有可交叉印证的依据。"
        if has_history:
            answer = f"{answer} 这个回答也结合了当前会话中的上下文。"
        answer = f"{answer} 请以最新版制度和模板为准。"
        return answer, 0.79, "answer"

    @staticmethod
    def _task_defaults(task_mode: str) -> dict[str, list[str]]:
        if task_mode == "procurement_fit_review":
            return {
                "source_type_hints": ["faq_csv", "markdown", "text"],
                "document_hints": ["采购核心", "供应商准入", "采购审批矩阵", "安全评审"],
                "domain_labels": ["procurement", "vendor_fit"],
            }
        if task_mode == "legal_contract_review":
            return {
                "source_type_hints": ["markdown", "text"],
                "document_hints": ["法务核心", "合同边界", "模板要求", "风险处理", "审查说明"],
                "domain_labels": ["legal", "contract_review"],
            }
        return {
            "source_type_hints": ["faq_csv", "markdown", "text"],
            "document_hints": ["常见问答", "制度", "流程", "清单"],
            "domain_labels": ["knowledge_qa"],
        }

    @staticmethod
    def _has_conflict(citations: list[Citation]) -> bool:
        snippets = [citation.snippet.lower() for citation in citations[:4]]
        negative_markers = ("不得", "不能", "禁止", "must not", "shall not", "not permitted")
        positive_markers = ("可以", "允许", "may", "can", "required", "must")
        positives = sum(1 for snippet in snippets if any(marker in snippet for marker in positive_markers))
        negatives = sum(1 for snippet in snippets if any(marker in snippet for marker in negative_markers))
        return positives > 0 and negatives > 0 and len({citation.document_title for citation in citations}) > 1

    @staticmethod
    def _first_sentence(text: str) -> str:
        for marker in ("回答：", "回答:", "Answer:", "answer:"):
            if marker in text:
                answer_text = text.split(marker, 1)[1].strip()
                if answer_text:
                    text = answer_text
                    break
        sentences = [sentence.strip() for sentence in SENTENCE_PATTERN.split(text) if sentence.strip()]
        if not sentences:
            return text[:180]
        return sentences[0]

    @staticmethod
    def _is_out_of_scope_query(query: str) -> bool:
        lowered = query.lower()
        return any(
            token in lowered
            for token in [
                "帮我决定签不签",
                "直接批准",
                "帮我谈判价格",
                "give me negotiation strategy",
                "what price should i accept",
                "替我做法务结论",
                "legal opinion",
            ]
        )

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        return [item for item in dict.fromkeys(str(item).strip() for item in items) if item]
