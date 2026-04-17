from __future__ import annotations


def test_evaluation_case_crud_and_filtered_run(client, auth_headers):
    admin_headers = auth_headers("admin")

    create_case = client.post(
        "/eval/cases",
        headers=admin_headers,
        json={
            "question": "比较标准主服务协议与供应商回传红线版本在核心条款上的差异。",
            "expected_answer": "供应商回传版本弱化了责任上限，并放松了数据处理和安全事件通知约束。",
            "expected_document_title": "法务核心-标准主服务协议模板.md",
            "task_type": "compare",
            "required_role": "manager",
            "knowledge_domain": "contract_review",
        },
    )
    assert create_case.status_code == 200
    created = create_case.json()
    assert created["knowledge_domain"] == "contract_review"

    list_cases = client.get("/eval/cases", headers=admin_headers, params={"knowledge_domains": "contract_review"})
    assert list_cases.status_code == 200
    assert any(case["id"] == created["id"] for case in list_cases.json())

    run = client.post(
        "/eval/run",
        headers=admin_headers,
        json={
            "case_ids": [created["id"]],
            "task_types": [],
            "required_roles": [],
            "knowledge_domains": [],
        },
    )
    assert run.status_code == 200
    payload = run.json()
    assert payload["status"] == "completed"
    assert payload["result_count"] == 1
    assert "answer_action_accuracy" in payload["metrics"]
    assert "insufficient_evidence_refusal_rate" in payload["metrics"]
    assert "filters" in payload
    assert payload["results"]
