from __future__ import annotations


def test_query_returns_citations_trace_and_debug_summary(client):
    response = client.post(
        "/chat/query",
        json={
            "query": "供应商准入前必须收集哪些基础材料？",
            "user_role": "employee",
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["citations"]
    assert payload["trace_id"]
    assert payload["next_action"] in {"answer", "clarify", "refuse"}
    assert "retrieval" in payload["debug_summary"]
    assert "verification" in payload["debug_summary"]

    trace = client.get(f"/trace/{payload['trace_id']}")
    assert trace.status_code == 200
    trace_payload = trace.json()
    assert len(trace_payload["steps"]) == 5
    assert trace_payload["debug_summary"]["intent"] in {"qa", "compare", "workflow", "support"}


def test_trace_search_can_find_failed_guest_queries(client):
    response = client.post(
        "/chat/query",
        json={
            "query": "哪些情况必须升级法务审批？",
            "user_role": "guest",
            "top_k": 5,
        },
    )
    assert response.status_code == 200

    trace_search = client.get("/trace/search", params={"failed_only": True, "user_role": "guest"})
    assert trace_search.status_code == 200
    payload = trace_search.json()
    assert payload
    assert any(item["trace_id"] == response.json()["trace_id"] for item in payload)
