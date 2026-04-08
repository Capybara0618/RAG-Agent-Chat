from __future__ import annotations


def test_evaluation_case_crud_and_filtered_run(client):
    create_case = client.post(
        "/eval/cases",
        json={
            "question": "Compare the standard MSA with the vendor redline version on core legal clauses.",
            "expected_answer": "The vendor redline weakens liability and omits several core clauses such as audit rights or termination protections.",
            "expected_document_title": "procurement_cn_standard_msa_template.md",
            "task_type": "compare",
            "required_role": "employee",
            "knowledge_domain": "contract_review",
        },
    )
    assert create_case.status_code == 200
    created = create_case.json()
    assert created["knowledge_domain"] == "contract_review"

    list_cases = client.get("/eval/cases", params={"knowledge_domains": "contract_review"})
    assert list_cases.status_code == 200
    assert any(case["id"] == created["id"] for case in list_cases.json())

    run = client.post(
        "/eval/run",
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
