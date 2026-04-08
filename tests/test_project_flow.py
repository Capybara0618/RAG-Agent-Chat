from __future__ import annotations


def test_project_flow_creation_stage_progression_and_review(client):
    create_response = client.post(
        "/projects",
        json={
            "title": "AlphaDesk SaaS Procurement",
            "requester_name": "Alice",
            "department": "Customer Support",
            "vendor_name": "AlphaDesk",
            "category": "software",
            "budget_amount": 1200000,
            "currency": "CNY",
            "summary": "Procure a customer support SaaS platform with customer data exposure.",
            "data_scope": "customer_data",
        },
    )
    assert create_response.status_code == 200, create_response.text
    project = create_response.json()
    project_id = project["id"]
    assert project["current_stage"] == "draft"
    assert project["tasks"]
    assert project["blocker_summary"]

    blocked_advance = client.post(f"/projects/{project_id}/advance", json={})
    assert blocked_advance.status_code == 400

    for task in project["tasks"]:
        update_response = client.patch(
            f"/projects/{project_id}/tasks/{task['id']}",
            json={"status": "done"},
        )
        assert update_response.status_code == 200, update_response.text

    advance_response = client.post(f"/projects/{project_id}/advance", json={})
    assert advance_response.status_code == 200, advance_response.text
    advanced_project = advance_response.json()
    assert advanced_project["current_stage"] == "vendor_onboarding"
    assert advanced_project["artifacts"]

    review_response = client.post(
        f"/projects/{project_id}/review/query",
        json={
            "query": "What mandatory materials are still required before vendor onboarding can proceed?",
            "user_role": "employee",
            "top_k": 5,
        },
    )
    assert review_response.status_code == 200, review_response.text
    review_payload = review_response.json()
    assert review_payload["review"]["trace_id"]
    assert review_payload["project"]["chat_session_id"]

    timeline_response = client.get(f"/projects/{project_id}/timeline")
    assert timeline_response.status_code == 200, timeline_response.text
    timeline = timeline_response.json()
    assert timeline
    assert any(item["kind"] == "stage" for item in timeline)
    assert any(item["kind"] == "decision" for item in timeline)

