from __future__ import annotations


def test_guest_cannot_access_employee_only_documents(client):
    response = client.post(
        "/chat/query",
        json={
            "query": "What is required for remote access?",
            "user_role": "guest",
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["next_action"] in {"clarify", "refuse"}
    assert payload["citations"] == []