from __future__ import annotations


def test_evaluation_run_completes(client):
    response = client.post("/eval/run", json={"case_ids": []})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["result_count"] >= 1
    assert "recall_at_k" in payload["metrics"]