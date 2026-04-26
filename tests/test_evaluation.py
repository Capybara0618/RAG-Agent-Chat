from __future__ import annotations

from app.services.evaluation.procurement_review_cases import PROCUREMENT_REVIEW_EVAL_CASES


def test_evaluation_case_crud_and_filtered_run(client, auth_headers):
    admin_headers = auth_headers("admin")

    create_case = client.post(
        "/eval/cases",
        headers=admin_headers,
        json={
            "question": "项目预算 60 万，但供应商报价已经到 85 万，业务又很着急上线，采购还能直接往下推吗？",
            "expected_answer": "不能直接往下推。预算明显超出时应按审批矩阵升级处理，采购不能自行放行。",
            "expected_document_title": "采购核心-采购审批矩阵.md",
            "task_type": "support",
            "required_role": "procurement",
            "knowledge_domain": "procurement_approval",
        },
    )
    assert create_case.status_code == 200
    created = create_case.json()
    assert created["knowledge_domain"] == "procurement_approval"

    list_cases = client.get("/eval/cases", headers=admin_headers, params={"knowledge_domains": "procurement_approval"})
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


def test_procurement_review_eval_cases_have_expected_size():
    assert len(PROCUREMENT_REVIEW_EVAL_CASES) == 100
