from __future__ import annotations

import json
import time
from typing import Callable

from sqlalchemy.orm import Session

from app.services.agent.llm import LLMClient
from app.services.agent.types import AgentState
from app.services.retrieval.service import RetrievalService

try:
    from langgraph.graph import END, StateGraph
except ImportError:
    END = "__end__"

    class _CompiledGraph:
        def __init__(self, entry_point: str, nodes: dict[str, Callable[[AgentState], AgentState]], edges: dict[str, str]) -> None:
            self.entry_point = entry_point
            self.nodes = nodes
            self.edges = edges

        def invoke(self, state: AgentState) -> AgentState:
            current = self.entry_point
            while current != END:
                state = self.nodes[current](state)
                current = self.edges[current]
            return state

    class StateGraph:
        def __init__(self, _: object) -> None:
            self.nodes: dict[str, Callable[[AgentState], AgentState]] = {}
            self.edges: dict[str, str] = {}
            self.entry_point = ""

        def add_node(self, name: str, fn: Callable[[AgentState], AgentState]) -> None:
            self.nodes[name] = fn

        def add_edge(self, start: str, end: str) -> None:
            self.edges[start] = end

        def set_entry_point(self, name: str) -> None:
            self.entry_point = name

        def compile(self) -> _CompiledGraph:
            return _CompiledGraph(self.entry_point, self.nodes, self.edges)


class KnowledgeGraphBuilder:
    def __init__(self, *, llm_client: LLMClient, retrieval_service: RetrievalService) -> None:
        self.llm_client = llm_client
        self.retrieval_service = retrieval_service

    def build(self, db: Session):
        graph = StateGraph(AgentState)
        graph.add_node("intent_router", self._wrap("意图路由", lambda state: self.intent_router(state)))
        graph.add_node("retrieval_planner", self._wrap("检索规划", lambda state: self.retrieval_planner(state)))
        graph.add_node("tool_executor", self._wrap("检索执行", lambda state: self.tool_executor(state, db)))
        graph.add_node("answer_composer", self._wrap("答案生成", lambda state: self.answer_composer(state)))
        graph.add_node("citation_verifier", self._wrap("引用校验", lambda state: self.citation_verifier(state)))
        graph.set_entry_point("intent_router")
        graph.add_edge("intent_router", "retrieval_planner")
        graph.add_edge("retrieval_planner", "tool_executor")
        graph.add_edge("tool_executor", "answer_composer")
        graph.add_edge("answer_composer", "citation_verifier")
        graph.add_edge("citation_verifier", END)
        return graph.compile()

    def _wrap(self, node_name: str, func: Callable[[AgentState], AgentState]) -> Callable[[AgentState], AgentState]:
        def runner(state: AgentState) -> AgentState:
            started = time.perf_counter()
            try:
                new_state = func(state)
                success = True
            except Exception as exc:
                new_state = state.copy()
                new_state["next_action"] = "clarify"
                new_state["final_answer"] = f"工作流在“{node_name}”阶段发生降级：{exc}"
                success = False
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            trace_steps = list(new_state.get("trace_steps", []))
            trace_steps.append(
                {
                    "node_name": node_name,
                    "input_summary": self._summarize_input(node_name, state),
                    "output_summary": self._summarize_output(node_name, new_state),
                    "latency_ms": latency_ms,
                    "success": success,
                }
            )
            new_state["trace_steps"] = trace_steps
            return new_state

        return runner

    def intent_router(self, state: AgentState) -> AgentState:
        intent, confidence = self.llm_client.classify_intent(state["query"])
        state["intent"] = intent
        state["intent_confidence"] = confidence
        return state

    def retrieval_planner(self, state: AgentState) -> AgentState:
        plan = self.llm_client.build_retrieval_plan(state["query"], state["intent"], state["top_k"])
        state["retrieval_plan"] = plan
        return state

    def tool_executor(self, state: AgentState, db: Session) -> AgentState:
        plan = state["retrieval_plan"]
        retrieved, retrieval_debug = self.search_knowledge(db, state)
        state["retrieved_chunks"] = retrieved
        state["retrieval_debug"] = retrieval_debug
        state["citations"] = self.retrieval_service.to_citations(retrieved)
        state["compressed_context"] = self.retrieval_service.compress_context(retrieved)

        if plan.get("allow_multi_doc"):
            document_ids = list(dict.fromkeys(chunk.document_id for chunk in retrieved[:3]))
            state["comparison_view"] = self.compare_evidence(
                self.fetch_document_sections(db, document_ids=document_ids)
            )
        return state

    def search_knowledge(self, db: Session, state: AgentState):
        return self.retrieval_service.retrieve(
            db,
            query=state["query"],
            user_role=state["user_role"],
            top_k=int(state["retrieval_plan"]["top_k"]),
            plan=state["retrieval_plan"],
        )

    def fetch_document_sections(self, db: Session, *, document_ids: list[str]):
        return self.retrieval_service.fetch_document_sections(db, document_ids)

    def compare_evidence(self, chunks):
        return self.retrieval_service.compare_evidence(chunks)

    def answer_composer(self, state: AgentState) -> AgentState:
        answer, confidence, next_action = self.llm_client.compose_answer(
            query=state["query"],
            intent=state["intent"],
            citations=list(state.get("citations", [])),
            retrieved_chunks=list(state.get("retrieved_chunks", [])),
            comparison_view=state.get("comparison_view"),
            history=state["history"],
        )
        state["draft_answer"] = answer
        state["confidence"] = confidence
        state["next_action"] = next_action
        return state

    def citation_verifier(self, state: AgentState) -> AgentState:
        answer = str(state.get("draft_answer", ""))
        citations = list(state.get("citations", []))
        verified_confidence, verified_action, verification_debug = self.llm_client.verify_citations(answer, citations)
        state["confidence"] = round(min(state.get("confidence", 0.0), verified_confidence), 2)
        if verified_action != "answer":
            state["next_action"] = verified_action
            if verification_debug.get("has_conflict"):
                answer = f"{answer}\n\n说明：当前引用到的多份资料存在潜在冲突，建议进一步确认适用的制度版本或部门范围。"
        state["verification_debug"] = verification_debug
        state["final_answer"] = answer
        state["debug_summary"] = {
            "intent": state.get("intent", "qa"),
            "intent_confidence": state.get("intent_confidence", 0.0),
            "retrieval_plan": state.get("retrieval_plan", {}),
            "retrieval": state.get("retrieval_debug", {}),
            "comparison_view": state.get("comparison_view", {}),
            "verification": verification_debug,
        }
        return state

    @staticmethod
    def _summarize_input(node_name: str, state: AgentState) -> str:
        if node_name == "意图路由":
            return state["query"][:160]
        if node_name == "检索执行":
            plan = state.get("retrieval_plan", {})
            return f"召回数量={plan.get('top_k')} 角色={state.get('user_role')}"
        return f"意图={state.get('intent', '')} 问题={state['query'][:80]}"

    @staticmethod
    def _summarize_output(node_name: str, state: AgentState) -> str:
        if node_name == "意图路由":
            return f"意图={state.get('intent', '')} 置信度={state.get('intent_confidence', 0.0)}"
        if node_name == "检索规划":
            return json.dumps(state.get("retrieval_plan", {}), ensure_ascii=False)
        if node_name == "检索执行":
            retrieval_debug = state.get("retrieval_debug", {})
            return json.dumps(
                {
                    "citation_count": len(state.get("citations", [])),
                    "retrieval": retrieval_debug,
                },
                ensure_ascii=False,
            )
        if node_name == "答案生成":
            return f"系统动作={state.get('next_action', '')} 置信度={state.get('confidence', 0.0)}"
        return json.dumps(state.get("verification_debug", {}), ensure_ascii=False)
