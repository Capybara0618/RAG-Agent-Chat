from __future__ import annotations


def test_query_returns_citations_and_trace(client):
    response = client.post(
        "/chat/query",
        json={
            "query": "What should a new employee complete before receiving production access?",
            "user_role": "employee",
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["citations"]
    assert payload["trace_id"]
    assert payload["next_action"] in {"answer", "clarify", "refuse"}

    trace = client.get(f"/trace/{payload['trace_id']}")
    assert trace.status_code == 200
    trace_payload = trace.json()
    assert len(trace_payload["steps"]) == 5