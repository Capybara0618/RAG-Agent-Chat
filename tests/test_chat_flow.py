from __future__ import annotations


def test_query_returns_citations_trace_and_debug_summary(client, auth_headers):
    procurement_headers = auth_headers("procurement")
    admin_headers = auth_headers("admin")

    response = client.post(
        "/chat/query",
        headers=procurement_headers,
        json={
            "query": "供应商准入前必须收集哪些基础材料？",
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["citations"]
    assert payload["trace_id"]
    assert payload["next_action"] in {"answer", "clarify", "refuse"}
    assert payload["tool_calls"]
    assert payload["debug_summary"]["tool_calls"]
    assert "retrieval" in payload["debug_summary"]
    assert "verification" in payload["debug_summary"]

    trace = client.get(f"/trace/{payload['trace_id']}", headers=admin_headers)
    assert trace.status_code == 200
    trace_payload = trace.json()
    assert len(trace_payload["steps"]) == 4
    assert trace_payload["debug_summary"]["task_mode"] == "knowledge_qa"
    assert trace_payload["debug_summary"]["intent"] == "knowledge_qa"


def test_business_cannot_use_internal_assistant_and_non_admin_cannot_search_trace(client, auth_headers):
    business_headers = auth_headers("business")
    procurement_headers = auth_headers("procurement")

    query_response = client.post(
        "/chat/query",
        headers=business_headers,
        json={"query": "哪些情况必须升级法务审批？", "top_k": 5},
    )
    assert query_response.status_code == 403

    trace_search = client.get("/trace/search", headers=procurement_headers, params={"failed_only": True})
    assert trace_search.status_code == 403
