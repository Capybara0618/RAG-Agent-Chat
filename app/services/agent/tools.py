from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.schemas.common import ToolCallRead
from app.services.agent.types import AgentState
from app.services.retrieval.service import RetrievalService


@dataclass
class AgentToolExecution:
    state_updates: dict[str, object]
    output_summary: str


class AgentTool:
    def __init__(self, *, name: str, purpose: str) -> None:
        self.name = name
        self.purpose = purpose

    def execute(
        self,
        *,
        state: AgentState,
        db: Session,
        retrieval_service: RetrievalService,
    ) -> AgentToolExecution:
        raise NotImplementedError


class KnowledgeSearchTool(AgentTool):
    def execute(
        self,
        *,
        state: AgentState,
        db: Session,
        retrieval_service: RetrievalService,
    ) -> AgentToolExecution:
        plan = state["retrieval_plan"]
        retrieved, retrieval_debug = retrieval_service.retrieve(
            db,
            query=state["query"],
            user_role=state["user_role"],
            top_k=int(plan["top_k"]),
            plan=plan,
        )
        citations = retrieval_service.to_citations(retrieved)
        compressed_context = retrieval_service.compress_context(retrieved)
        return AgentToolExecution(
            state_updates={
                "retrieved_chunks": retrieved,
                "retrieval_debug": retrieval_debug,
                "citations": citations,
                "compressed_context": compressed_context,
            },
            output_summary=f"召回 {len(retrieved)} 个片段，生成 {len(citations)} 条引用",
        )


class EvidenceCompareTool(AgentTool):
    def execute(
        self,
        *,
        state: AgentState,
        db: Session,
        retrieval_service: RetrievalService,
    ) -> AgentToolExecution:
        retrieved = list(state.get("retrieved_chunks", []))
        document_ids = list(dict.fromkeys(chunk.document_id for chunk in retrieved[:3]))
        if len(document_ids) < 2:
            return AgentToolExecution(
                state_updates={"comparison_view": {"risk_flags": [], "missing_clauses": {}, "clause_matrix": {}}},
                output_summary=f"命中文档不足 2 份，当前仅保留 {len(document_ids)} 份证据，不执行深度对比",
            )
        sections = retrieval_service.fetch_document_sections(db, document_ids=document_ids)
        comparison_view = retrieval_service.compare_evidence(sections)
        risk_flags = list(comparison_view.get("risk_flags", [])) if isinstance(comparison_view, dict) else []
        return AgentToolExecution(
            state_updates={"comparison_view": comparison_view},
            output_summary=f"对比 {len(document_ids)} 份文档，识别 {len(risk_flags)} 个风险信号",
        )


def build_tool_registry() -> dict[str, AgentTool]:
    tools: list[AgentTool] = [
        KnowledgeSearchTool(name="knowledge_search", purpose="检索内部制度、模板和流程依据"),
        EvidenceCompareTool(name="evidence_compare", purpose="对多文档证据做条款差异和风险对比"),
        KnowledgeSearchTool(name="retrieve_procurement_knowledge", purpose="检索采购准入制度、审批矩阵、安全评审和供应商治理依据"),
        EvidenceCompareTool(name="compare_procurement_evidence", purpose="对采购命中的多份制度或材料证据做差异比对"),
        KnowledgeSearchTool(name="retrieve_legal_redlines", purpose="检索法务红线、合同模板和条款审查依据"),
        EvidenceCompareTool(name="compare_legal_clauses", purpose="对合同和红线证据做条款差异与风险对比"),
    ]
    return {tool.name: tool for tool in tools}


def build_tool_call(
    *,
    tool_name: str,
    purpose: str,
    status: str,
    input_summary: str,
    output_summary: str,
) -> ToolCallRead:
    return ToolCallRead(
        tool_name=tool_name,
        purpose=purpose,
        status=status,
        input_summary=input_summary,
        output_summary=output_summary,
    )
