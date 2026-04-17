from __future__ import annotations

import json
import re

import httpx

from app.schemas.common import Citation
from app.services.agent.providers import LLMProvider
from app.services.retrieval.embeddings import tokenize_text
from app.services.retrieval.service import RetrievedChunk


SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s*")


class LLMClient(LLMProvider):
    def __init__(self, *, api_base: str = "", api_key: str = "", model: str = "") -> None:
        self.api_base = api_base
        self.api_key = api_key
        self.model = model

    def classify_intent(self, query: str) -> tuple[str, float]:
        lowered = query.lower()
        if any(
            token in lowered
            for token in ["compare", "difference", "redline", "redlines", "vs", "versus", "对比", "差异", "红线", "条款区别"]
        ):
            return "compare", 0.91
        if any(
            token in lowered
            for token in ["workflow", "process", "steps", "approval flow", "审批流程", "流程", "步骤", "怎么处理", "升级给谁"]
        ):
            return "workflow", 0.87
        if any(
            token in lowered
            for token in [
                "vendor",
                "supplier",
                "msa",
                "nda",
                "dpa",
                "security review",
                "onboarding",
                "due diligence",
                "procurement",
                "供应商",
                "采购",
                "合同",
                "准入",
                "尽调",
                "法务",
                "安全评审",
                "付款条款",
            ]
        ):
            return "support", 0.84
        return "qa", 0.67

    def route_intent(self, query: str) -> str:
        intent, _ = self.classify_intent(query)
        return intent

    def build_retrieval_plan(self, query: str, intent: str, top_k: int) -> dict[str, object]:
        procurement_hints = self._procurement_hints(query)
        query_variants = [query, *procurement_hints["query_variants"]]
        source_type_hints = ["markdown", "text", "faq_csv"]

        if intent == "compare":
            query_variants.extend([f"{query} 条款差异", f"{query} 红线对比", f"{query} contract deviations"])
        elif intent == "workflow":
            query_variants.extend([f"{query} 审批流程", f"{query} SOP", f"{query} escalation workflow"])
        elif intent == "support":
            query_variants.extend([f"{query} 要求", f"{query} policy requirement", f"{query} checklist"])
            source_type_hints = ["faq_csv", "markdown", "text"]

        deduped_variants = [item for item in dict.fromkeys(query_variants) if str(item).strip()]
        return {
            "intent": intent,
            "top_k": top_k + 1 if intent == "compare" else top_k,
            "rerank_k": max(top_k * 3, 10),
            "allow_multi_doc": intent in {"compare", "workflow"},
            "query_variants": deduped_variants,
            "source_type_hints": source_type_hints,
            "document_hints": procurement_hints["document_hints"],
            "domain_labels": procurement_hints["domain_labels"],
        }

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
        intent: str,
        citations: list[Citation],
        retrieved_chunks: list[RetrievedChunk],
        comparison_view: dict[str, object] | None,
        history: list[dict[str, str]],
    ) -> tuple[str, float, str]:
        if self._is_out_of_scope_query(query):
            return (
                "当前系统定位为采购合同审查与供应商准入助手，只回答制度、条款、审批和评审流程问题，不替代法务签批或商业谈判决策。",
                0.08,
                "refuse",
            )

        if not citations:
            if len(tokenize_text(query)) <= 8:
                return (
                    "我暂时无法在采购知识库里定位到足够证据。请补充合同类型、流程阶段，或说明是在问供应商准入、法务红线、安全评审还是审批矩阵。",
                    0.18,
                    "clarify",
                )
            return (
                "当前知识库没有足够可靠的采购制度或合同条款证据来安全回答这个问题。请上传相关合同模板、审查指引、准入制度或缩小问题范围。",
                0.12,
                "refuse",
            )

        if intent == "compare":
            return self._compose_compare_answer(query, comparison_view, retrieved_chunks)
        if intent == "workflow":
            return self._compose_workflow_answer(query, retrieved_chunks)
        if intent == "support":
            return self._compose_support_answer(query, retrieved_chunks)
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

    def _compose_compare_answer(
        self,
        query: str,
        comparison_view: dict[str, object] | None,
        retrieved_chunks: list[RetrievedChunk],
    ) -> tuple[str, float, str]:
        if comparison_view:
            clause_matrix = comparison_view.get("clause_matrix", {})
            missing_clauses = comparison_view.get("missing_clauses", {})
            risk_flags = comparison_view.get("risk_flags", [])
            lines = [f"条款对比结论：{query}"]

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

            lines.append("建议：若涉及责任上限、审计权、数据处理、分包限制等核心红线，应升级法务复核。")
            return "\n".join(lines), 0.85, "answer"

        grouped: dict[str, list[RetrievedChunk]] = {}
        for chunk in retrieved_chunks:
            grouped.setdefault(chunk.document_title, []).append(chunk)
        if len(grouped) < 2:
            return (
                "我找到了部分条款证据，但暂时不足以做出可靠的合同差异对比。请补充标准模板或供应商回传版本。",
                0.44,
                "clarify",
            )

        lines = [f"合同条款对比：{query}"]
        for title, chunks in list(grouped.items())[:3]:
            lines.append(f"- {title}：{self._first_sentence(chunks[0].content)}")
        lines.append("建议进一步按责任上限、赔偿、数据处理、审计权和终止条款逐项核对。")
        return "\n".join(lines), 0.79, "answer"

    def _compose_workflow_answer(self, query: str, retrieved_chunks: list[RetrievedChunk]) -> tuple[str, float, str]:
        steps: list[str] = []
        for chunk in retrieved_chunks[:4]:
            for sentence in SENTENCE_PATTERN.split(chunk.content):
                cleaned = sentence.strip()
                if cleaned and cleaned not in steps:
                    steps.append(cleaned)
                if len(steps) >= 4:
                    break
            if len(steps) >= 4:
                break

        if not steps:
            return (
                "我找到了相关制度，但还不足以稳定生成一份采购流程 SOP。请补充是供应商准入、合同盖章、法务红线审批还是安全评审场景。",
                0.34,
                "clarify",
            )

        lines = [f"建议流程：{query}"]
        for index, step in enumerate(steps, start=1):
            lines.append(f"{index}. {step}")
        lines.append("执行前请以最新审批矩阵、法务模板和安全评审流程为准。")
        return "\n".join(lines), 0.8, "answer"

    def _compose_support_answer(self, query: str, retrieved_chunks: list[RetrievedChunk]) -> tuple[str, float, str]:
        chunk = retrieved_chunks[0]
        lines = [
            f"问题：{query}",
            f"根据当前采购制度证据，答案是：{self._first_sentence(chunk.content)}",
            "下一步建议：先按引用制度或模板执行；若涉及责任上限放宽、赔偿范围扩大、数据出境、审计权缺失等红线，请升级法务或安全复核。",
            "边界提示：该回答用于内部审查辅助，不替代法务最终签批意见。",
        ]
        return "\n".join(lines), 0.81, "answer"

    def _compose_qa_answer(self, retrieved_chunks: list[RetrievedChunk], has_history: bool) -> tuple[str, float, str]:
        primary = retrieved_chunks[0]
        answer = self._first_sentence(primary.content)
        if len(retrieved_chunks) > 1:
            answer = f"{answer} 另外，{retrieved_chunks[1].document_title} 中也有可交叉印证的依据。"
        if has_history:
            answer = f"{answer} 这个回答也结合了当前会话中的上下文。"
        answer = f"{answer} 请以最新版模板、审批矩阵和签署口径为准。"
        return answer, 0.79, "answer"

    def _procurement_hints(self, query: str) -> dict[str, list[str]]:
        lowered = query.lower()
        query_variants: list[str] = []
        document_hints: list[str] = []
        domain_labels: list[str] = []

        if any(token in lowered for token in ["msa", "master service", "主协议", "主服务协议"]):
            query_variants.extend(["master service agreement clause review", "MSA liability audit termination data processing"])
            document_hints.extend(["msa", "master service agreement", "主服务协议", "template"])
            domain_labels.append("contract_review")
        if any(token in lowered for token in ["nda", "保密协议", "confidentiality"]):
            query_variants.extend(["nda confidentiality term mutual disclosure", "保密协议 保密义务 例外情形"])
            document_hints.extend(["nda", "保密协议", "confidentiality"])
            domain_labels.append("contract_review")
        if any(token in lowered for token in ["vendor", "supplier", "供应商", "准入", "onboarding", "due diligence", "尽调"]):
            query_variants.extend(["vendor onboarding due diligence checklist", "供应商准入 尽调 清单"])
            document_hints.extend(["vendor", "supplier", "供应商", "准入", "尽调"])
            domain_labels.append("vendor_onboarding")
        if any(token in lowered for token in ["security", "security review", "安全评审", "questionnaire", "iso", "soc2"]):
            query_variants.extend(["security review questionnaire infosec review", "安全评审 问卷 等保 数据处理"])
            document_hints.extend(["security", "infosec", "安全评审", "问卷"])
            domain_labels.append("security_due_diligence")
        if any(token in lowered for token in ["approval", "审批", "doa", "delegation", "matrix", "法务审批", "采购审批"]):
            query_variants.extend(["approval matrix delegation of authority", "审批矩阵 授权级别"])
            document_hints.extend(["approval matrix", "doa", "审批矩阵", "授权"])
            domain_labels.append("approval_workflow")
        if any(token in lowered for token in ["liability", "indemnity", "audit right", "termination", "责任上限", "赔偿", "审计权", "终止"]):
            query_variants.extend(["liability cap indemnity audit right termination", "责任上限 赔偿 审计权 终止"])
            document_hints.extend(["liability", "indemnity", "audit", "termination", "责任上限", "赔偿", "审计权"])
            domain_labels.append("legal_redlines")

        return {
            "query_variants": list(dict.fromkeys(query_variants)),
            "document_hints": list(dict.fromkeys(document_hints)),
            "domain_labels": list(dict.fromkeys(domain_labels)),
        }

    @staticmethod
    def _has_conflict(citations: list[Citation]) -> bool:
        snippets = [citation.snippet for citation in citations[:4]]
        negative_markers = ("不得", "不能", "禁止", "must not", "shall not", "not permitted")
        positive_markers = ("可以", "允许", "may", "can", "required", "must")
        positives = sum(1 for snippet in snippets if any(marker in snippet.lower() for marker in positive_markers))
        negatives = sum(1 for snippet in snippets if any(marker in snippet.lower() for marker in negative_markers))
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
