from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def api_get(path: str) -> Any:
    with httpx.Client(base_url=API_BASE_URL, timeout=20.0) as client:
        response = client.get(path)
        response.raise_for_status()
        return response.json()


def api_post(path: str, json_payload: dict[str, Any] | None = None, files: dict[str, Any] | None = None, data: dict[str, Any] | None = None) -> Any:
    with httpx.Client(base_url=API_BASE_URL, timeout=40.0) as client:
        response = client.post(path, json=json_payload, files=files, data=data)
        response.raise_for_status()
        return response.json()


def init_state() -> None:
    st.session_state.setdefault("session_id", None)
    st.session_state.setdefault("trace_id", "")


def render_chat_page() -> None:
    st.subheader("User Copilot")
    user_role = st.selectbox("Role", ["guest", "employee", "admin"], index=1)
    query = st.text_area("Ask a grounded knowledge question", height=120, placeholder="Compare onboarding requirements with remote access policy.")
    if st.button("Run Query", use_container_width=True):
        if not query.strip():
            st.warning("Please enter a question first.")
        else:
            response = api_post(
                "/chat/query",
                json_payload={
                    "query": query,
                    "session_id": st.session_state.session_id,
                    "user_role": user_role,
                    "top_k": 5,
                },
            )
            st.session_state.session_id = response["session_id"]
            st.session_state.trace_id = response["trace_id"]
            st.success(f"Intent: {response['intent']} | Next action: {response['next_action']} | Confidence: {response['confidence']}")
            st.markdown("### Answer")
            st.write(response["answer"])
            st.markdown("### Citations")
            for citation in response["citations"]:
                st.markdown(f"- **{citation['document_title']}** ({citation['location']}) score={citation['score']}")
                st.caption(citation["snippet"])

    if st.session_state.session_id:
        session = api_get(f"/chat/sessions/{st.session_state.session_id}")
        st.markdown("### Session History")
        for message in session["messages"]:
            label = "User" if message["role"] == "user" else "Assistant"
            st.markdown(f"**{label}:** {message['content']}")


def render_knowledge_page() -> None:
    st.subheader("Knowledge Sources")
    uploaded = st.file_uploader("Upload document", type=["md", "txt", "pdf", "docx", "csv"])
    remote_url = st.text_input("Or ingest a remote URL")
    allowed_roles = st.text_input("Allowed roles", value="guest,employee,admin")
    tags = st.text_input("Tags", value="handbook,policy")
    if st.button("Ingest Source", use_container_width=True):
        if uploaded is None and not remote_url.strip():
            st.warning("Provide a file or remote URL.")
        else:
            files = None
            data = {"allowed_roles": allowed_roles, "tags": tags, "remote_url": remote_url or None}
            if uploaded is not None:
                files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream")}
            response = api_post("/knowledge/upload", files=files, data=data)
            st.success(f"Indexed {response['source']['title']} with {response['chunk_count']} chunks.")

    if st.button("Reindex All", use_container_width=True):
        response = api_post("/knowledge/reindex", json_payload={"document_ids": []})
        st.info(response)

    sources = api_get("/knowledge/sources")
    st.markdown("### Current Sources")
    for source in sources:
        st.markdown(f"- **{source['title']}** | {source['source_type']} | roles={', '.join(source['allowed_roles'])} | tags={', '.join(source['tags'])}")


def render_trace_page() -> None:
    st.subheader("Trace Explorer")
    trace_id = st.text_input("Trace ID", value=st.session_state.trace_id)
    if st.button("Load Trace", use_container_width=True):
        if not trace_id.strip():
            st.warning("Enter a trace ID.")
        else:
            trace = api_get(f"/trace/{trace_id}")
            st.json({
                "query": trace["query"],
                "intent": trace["intent"],
                "next_action": trace["next_action"],
                "confidence": trace["confidence"],
            })
            for step in trace["steps"]:
                st.markdown(f"**{step['node_name']}** | {step['latency_ms']}ms | success={step['success']}")
                st.caption(f"Input: {step['input_summary']}")
                st.caption(f"Output: {step['output_summary']}")


def render_eval_page() -> None:
    st.subheader("Evaluation Center")
    if st.button("Run Evaluation", use_container_width=True):
        result = api_post("/eval/run", json_payload={"case_ids": []})
        st.success(f"Run {result['id']} finished with {result['result_count']} cases.")
        st.json(result["metrics"])
        if result["failure_examples"]:
            st.markdown("### Failure Examples")
            for item in result["failure_examples"]:
                st.json(item)


def main() -> None:
    st.set_page_config(page_title="KnowledgeOps Copilot", layout="wide")
    init_state()
    st.title("KnowledgeOps Copilot")
    st.caption("Auditable RAG + Agent demo for internship interviews.")

    page = st.sidebar.radio("Page", ["Chat", "Knowledge", "Trace", "Evaluation"])
    st.sidebar.markdown(f"API: `{API_BASE_URL}`")

    if page == "Chat":
        render_chat_page()
    elif page == "Knowledge":
        render_knowledge_page()
    elif page == "Trace":
        render_trace_page()
    else:
        render_eval_page()


if __name__ == "__main__":
    main()