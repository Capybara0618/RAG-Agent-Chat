from __future__ import annotations

import time

from app.services.agent.workflow import KnowledgeGraphBuilder
from scripts.eval_legal_smoke import (
    SCENARIOS,
    create_runtime_client,
    create_runtime_dir,
    login_headers,
    reach_legal_stage,
    upload_knowledge_base,
    upload_legal_contracts,
)


def mark(step: str, started: float) -> None:
    print(f"[legal-debug] {step} ok elapsed={time.perf_counter() - started:.2f}s", flush=True)


def main() -> None:
    runtime_dir = create_runtime_dir()
    started = time.perf_counter()
    print(f"[legal-debug] runtime_dir={runtime_dir.resolve()}", flush=True)
    with create_runtime_client(runtime_dir) as client:
        headers = {
            "admin": login_headers(client, "admin"),
            "business": login_headers(client, "business"),
            "manager": login_headers(client, "manager"),
            "procurement": login_headers(client, "procurement"),
            "legal": login_headers(client, "legal"),
        }
        mark("login", started)

        upload_knowledge_base(client, headers["admin"])
        mark("knowledge_upload", started)

        project = reach_legal_stage(client, headers["business"], headers["manager"], headers["procurement"])
        mark("reach_legal_stage", started)

        project = upload_legal_contracts(client, headers["legal"], project, SCENARIOS[0])
        mark("upload_legal_contracts", started)

        project_id = project["id"]
        container = client.app.state.container
        with container.session_factory() as db:
            project_service = container.project_service
            project_obj = project_service._require_project(db, project_id)
            vendor = project_service._require_selected_vendor(db, project_obj)
            comparison = project_service._build_uploaded_legal_contract_comparison(
                db,
                project=project_obj,
                vendor=vendor,
            )
            mark("build_uploaded_comparison", started)

            query = project_service._build_default_legal_review_query(
                db,
                project_obj,
                vendor,
                contract_comparison=comparison,
            )
            print(f"[legal-debug] query_len={len(query)}", flush=True)
            mark("build_query", started)

            builder = KnowledgeGraphBuilder(
                llm_client=container.agent_service.llm_client,
                retrieval_service=container.agent_service.retrieval_service,
            )
            state = {
                "query": query,
                "session_id": "debug-session",
                "user_role": "legal",
                "top_k": 5,
                "task_mode": "legal_contract_review",
                "requested_tools": ["retrieve_legal_redlines", "compare_legal_clauses"],
                "history": [],
                "trace_id": "debug-trace",
                "trace_steps": [],
            }

            print("[legal-debug] entering tool_selector", flush=True)
            state = builder.tool_selector(state)
            print(f"[legal-debug] tool_sequence={state.get('tool_sequence')}", flush=True)
            mark("tool_selector", started)

            print("[legal-debug] entering tool_executor", flush=True)
            state = builder.tool_executor(state, db)
            print(f"[legal-debug] citations={len(state.get('citations', []))}", flush=True)
            mark("tool_executor", started)

            print("[legal-debug] entering answer_composer", flush=True)
            state = builder.answer_composer(state)
            print(f"[legal-debug] next_action={state.get('next_action')}", flush=True)
            mark("answer_composer", started)

            print("[legal-debug] entering citation_verifier", flush=True)
            state = builder.citation_verifier(state)
            print(f"[legal-debug] final_next_action={state.get('next_action')}", flush=True)
            print(f"[legal-debug] final_answer={str(state.get('final_answer', ''))[:800]}", flush=True)
            mark("citation_verifier", started)


if __name__ == "__main__":
    main()
