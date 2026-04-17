from __future__ import annotations

import json
import time
from typing import Callable

from sqlalchemy.orm import Session

from app.services.agent.llm import LLMClient
from app.services.agent.tools import build_tool_call, build_tool_registry
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
        self.tool_registry = build_tool_registry()

    def build(self, db: Session):
        graph = StateGraph(AgentState)
        graph.add_node("intent_router", self._wrap("意图路由", lambda state: self.intent_router(state)))
        graph.add_node("tool_selector", self._wrap("工具选择", lambda state: self.tool_selector(state)))
        graph.add_node("tool_executor", self._wrap("检索执行", lambda state: self.tool_executor(state, db)))
        graph.add_node("answer_composer", self._wrap("答案生成", lambda state: self.answer_composer(state)))
        graph.add_node("citation_verifier", self._wrap("引用校验", lambda state: self.citation_verifier(state)))
        graph.set_entry_point("intent_router")
        graph.add_edge("intent_router", "tool_selector")
        graph.add_edge("tool_selector", "tool_executor")
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

    def tool_selector(self, state: AgentState) -> AgentState:
        retrieval_plan = self.llm_client.build_retrieval_plan(state["query"], state["intent"], state["top_k"])
        requested_tools = [tool_name for tool_name in list(state.get("requested_tools", [])) if tool_name]
        if requested_tools:
            tool_sequence = requested_tools
        else:
            tool_sequence = ["knowledge_search"]
            if retrieval_plan.get("allow_multi_doc"):
                tool_sequence.append("evidence_compare")
        state["retrieval_plan"] = retrieval_plan
        state["tool_sequence"] = tool_sequence
        return state

    def tool_executor(self, state: AgentState, db: Session) -> AgentState:
        tool_calls = list(state.get("tool_calls", []))
        for tool_name in list(state.get("tool_sequence", [])):
            if not tool_name:
                continue
            tool = self.tool_registry.get(tool_name)
            if tool is None:
                tool_calls.append(
                    build_tool_call(
                        tool_name=tool_name,
                        purpose="未注册工具",
                        status="error",
                        input_summary=f"意图={state.get('intent', '')}",
                        output_summary="未找到对应工具定义。",
                    )
                )
                continue
            execution = tool.execute(
                state=state,
                db=db,
                retrieval_service=self.retrieval_service,
            )
            state.update(execution.state_updates)
            tool_calls.append(
                build_tool_call(
                    tool_name=tool_name,
                    purpose=tool.purpose,
                    status="success",
                    input_summary=self._summarize_tool_input(tool_name, state),
                    output_summary=execution.output_summary,
                )
            )
        state["tool_calls"] = tool_calls
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
            "tool_sequence": list(state.get("tool_sequence", [])),
            "tool_calls": [tool_call.model_dump() for tool_call in list(state.get("tool_calls", []))],
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
        if node_name == "工具选择":
            return json.dumps({"tool_sequence": list(state.get("tool_sequence", []))}, ensure_ascii=False)
        if node_name == "检索执行":
            retrieval_debug = state.get("retrieval_debug", {})
            return json.dumps(
                {
                    "tool_count": len(state.get("tool_calls", [])),
                    "citation_count": len(state.get("citations", [])),
                    "retrieval": retrieval_debug,
                },
                ensure_ascii=False,
            )
        if node_name == "答案生成":
            return f"系统动作={state.get('next_action', '')} 置信度={state.get('confidence', 0.0)}"
        return json.dumps(state.get("verification_debug", {}), ensure_ascii=False)

    @staticmethod
    def _summarize_tool_input(tool_name: str, state: AgentState) -> str:
        if tool_name in {"knowledge_search", "retrieve_procurement_knowledge", "retrieve_legal_redlines"}:
            plan = state.get("retrieval_plan", {})
            return f"query={state.get('query', '')[:80]} top_k={plan.get('top_k')}"
        if tool_name in {"evidence_compare", "compare_procurement_evidence", "compare_legal_clauses"}:
            return f"documents={len(list(state.get('retrieved_chunks', []))[:3])}"
        return state.get("query", "")[:80]
