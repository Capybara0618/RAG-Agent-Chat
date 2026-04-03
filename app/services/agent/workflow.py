from __future__ import annotations

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
        graph.add_node("intent_router", self._wrap("Intent Router", lambda state: self.intent_router(state)))
        graph.add_node("retrieval_planner", self._wrap("Retrieval Planner", lambda state: self.retrieval_planner(state)))
        graph.add_node("tool_executor", self._wrap("Tool Executor", lambda state: self.tool_executor(state, db)))
        graph.add_node("answer_composer", self._wrap("Answer Composer", lambda state: self.answer_composer(state)))
        graph.add_node("citation_verifier", self._wrap("Citation Verifier", lambda state: self.citation_verifier(state)))
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
                new_state["final_answer"] = f"Workflow degraded at {node_name}: {exc}"
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
        state["intent"] = self.llm_client.route_intent(state["query"])
        return state

    def retrieval_planner(self, state: AgentState) -> AgentState:
        state["retrieval_plan"] = self.llm_client.build_retrieval_plan(state["query"], state["intent"], state["top_k"])
        return state

    def tool_executor(self, state: AgentState, db: Session) -> AgentState:
        plan = state["retrieval_plan"]
        retrieved = self.retrieval_service.retrieve(
            db,
            query=str(plan["query"]),
            user_role=state["user_role"],
            top_k=int(plan["top_k"]),
        )
        state["retrieved_chunks"] = retrieved
        state["citations"] = self.retrieval_service.to_citations(retrieved)
        state["compressed_context"] = self.retrieval_service.compress_context(retrieved)
        return state

    def answer_composer(self, state: AgentState) -> AgentState:
        answer, confidence, next_action = self.llm_client.compose_answer(
            query=state["query"],
            intent=state["intent"],
            citations=list(state.get("citations", [])),
            retrieved_chunks=list(state.get("retrieved_chunks", [])),
            history=state["history"],
        )
        state["draft_answer"] = answer
        state["confidence"] = confidence
        state["next_action"] = next_action
        return state

    def citation_verifier(self, state: AgentState) -> AgentState:
        answer = str(state.get("draft_answer", ""))
        citations = list(state.get("citations", []))
        verified_confidence, verified_action = self.llm_client.verify_citations(answer, citations)
        state["confidence"] = round(min(state.get("confidence", 0.0), verified_confidence), 2)
        if verified_action != "answer":
            state["next_action"] = verified_action
        state["final_answer"] = answer
        return state

    @staticmethod
    def _summarize_input(node_name: str, state: AgentState) -> str:
        if node_name == "Intent Router":
            return state["query"][:160]
        if node_name == "Tool Executor":
            plan = state.get("retrieval_plan", {})
            return f"top_k={plan.get('top_k')} role={state.get('user_role')}"
        return f"intent={state.get('intent', '')} query={state['query'][:80]}"

    @staticmethod
    def _summarize_output(node_name: str, state: AgentState) -> str:
        if node_name == "Intent Router":
            return f"intent={state.get('intent', '')}"
        if node_name == "Retrieval Planner":
            plan = state.get("retrieval_plan", {})
            return f"plan={plan}"
        if node_name == "Tool Executor":
            return f"citations={len(state.get('citations', []))}"
        if node_name == "Answer Composer":
            return f"next_action={state.get('next_action', '')} confidence={state.get('confidence', 0.0)}"
        return f"verified_action={state.get('next_action', '')} confidence={state.get('confidence', 0.0)}"