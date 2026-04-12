from __future__ import annotations


def create_project(client, headers, **overrides):
    payload = {
        "title": "AlphaDesk SaaS Procurement",
        "requester_name": "Alice",
        "department": "Customer Support",
        "vendor_name": "AlphaDesk",
        "category": "software",
        "budget_amount": 1200000,
        "currency": "CNY",
        "summary": "Procure a customer support SaaS platform with customer data exposure.",
        "business_value": "Standardize service operations and improve ticket response time.",
        "target_go_live_date": "2026-06-30",
        "data_scope": "customer_data",
    }
    payload.update(overrides)
    response = client.post(
        "/projects",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


def get_project(client, headers, project_id):
    response = client.get(f"/projects/{project_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def complete_current_stage(client, headers, project):
    project_id = project["id"]
    current_stage = project["current_stage"]
    for task in project["tasks"]:
        if task["stage"] != current_stage or task["status"] == "done":
            continue
        response = client.patch(
            f"/projects/{project_id}/tasks/{task['id']}",
            headers=headers,
            json={"status": "done"},
        )
        assert response.status_code == 200, response.text
    for artifact in project["artifacts"]:
        if artifact["stage"] != current_stage or artifact["status"] in {"provided", "approved"}:
            continue
        response = client.patch(
            f"/projects/{project_id}/artifacts/{artifact['id']}",
            headers=headers,
            json={"status": "provided"},
        )
        assert response.status_code == 200, response.text
    return get_project(client, headers, project_id)


def reach_procurement_stage(client, auth_headers):
    business_headers = auth_headers("business")
    manager_headers = auth_headers("manager")
    procurement_headers = auth_headers("procurement")

    project = create_project(client, business_headers)
    project_id = project["id"]

    response = client.post(f"/projects/{project_id}/submit", headers=business_headers, json={"reason": ""})
    assert response.status_code == 200, response.text

    project = response.json()
    assert project["current_stage"] == "manager_review"
    assert project["blocker_summary"] == []
    response = client.post(
        f"/projects/{project_id}/manager-decision",
        headers=manager_headers,
        json={"decision": "approve", "reason": "审批通过"},
    )
    assert response.status_code == 200, response.text
    project = response.json()
    assert project["current_stage"] == "procurement_sourcing"
    return project, business_headers, manager_headers, procurement_headers


def test_withdraw_and_manager_return_keep_project_history(client, auth_headers):
    business_headers = auth_headers("business")
    manager_headers = auth_headers("manager")
    project = create_project(client, business_headers, business_value="", target_go_live_date="")
    project_id = project["id"]
    assert project["current_stage"] == "business_draft"
    assert project["draft_editable"] is True
    assert project["vendors"] == []
    assert project["application_form_ready"] is False
    assert any(item["key"] == "business_value" and item["checked"] is False for item in project["application_checks"])
    assert any(item["key"] == "target_go_live_date" and item["checked"] is False for item in project["application_checks"])

    update_response = client.patch(
        f"/projects/{project_id}",
        headers=business_headers,
        json={
            "title": "AlphaDesk SaaS Procurement Updated",
            "budget_amount": 1500000,
            "summary": "Updated summary for draft editing.",
            "vendor_name": "AlphaDesk Prime",
            "business_value": "Improve response efficiency and unify service process.",
            "target_go_live_date": "2026-07-15",
        },
    )
    assert update_response.status_code == 200, update_response.text
    updated_project = update_response.json()
    assert updated_project["title"] == "AlphaDesk SaaS Procurement Updated"
    assert updated_project["budget_amount"] == 1500000
    assert updated_project["summary"] == "Updated summary for draft editing."
    assert updated_project["application_form_ready"] is True
    assert all(item["checked"] for item in updated_project["application_checks"])
    current_task = next(task for task in updated_project["tasks"] if task["stage"] == "business_draft" and task["title"] == "填写并确认采购申请表")
    current_artifact = next(
        artifact for artifact in updated_project["artifacts"] if artifact["stage"] == "business_draft" and artifact["artifact_type"] == "procurement_application_form"
    )
    assert current_task["status"] == "done"
    assert current_artifact["status"] == "provided"

    blocked_submit = client.post(f"/projects/{project_id}/submit", headers=business_headers, json={"reason": ""})
    assert blocked_submit.status_code == 200, blocked_submit.text
    project = blocked_submit.json()
    assert project["current_stage"] == "manager_review"

    withdrawn = client.post(
        f"/projects/{project_id}/withdraw",
        headers=business_headers,
        json={"reason": "发现申请信息填写错误"},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    project = withdrawn.json()
    assert project["current_stage"] == "business_draft"
    assert project["id"] == project_id

    resubmitted = client.post(f"/projects/{project_id}/submit", headers=business_headers, json={"reason": ""})
    assert resubmitted.status_code == 200, resubmitted.text
    returned = client.post(
        f"/projects/{project_id}/manager-decision",
        headers=manager_headers,
        json={"decision": "return", "reason": "预算依据不足"},
    )
    assert returned.status_code == 200, returned.text
    project = returned.json()
    assert project["current_stage"] == "business_draft"

    timeline = client.get(f"/projects/{project_id}/timeline", headers=business_headers)
    assert timeline.status_code == 200, timeline.text
    items = timeline.json()
    assert any(item["kind"] == "stage" and "withdraw" in item["title"] for item in items)
    assert any(item["kind"] == "decision" and "manager_review" in item["title"] for item in items)


def test_multi_vendor_review_and_legal_return_to_procurement(client, auth_headers):
    project, _business_headers, _manager_headers, procurement_headers = reach_procurement_stage(client, auth_headers)
    legal_headers = auth_headers("legal")
    project_id = project["id"]

    create_vendor_response = client.post(
        f"/projects/{project_id}/vendors",
        headers=procurement_headers,
        json={
            "vendor_name": "ServiceNova",
            "source_platform": "企查查",
            "source_url": "https://example.com/service-nova",
            "profile_summary": "候选供应商二",
            "procurement_notes": "作为备选方案",
        },
    )
    assert create_vendor_response.status_code == 200, create_vendor_response.text

    project = get_project(client, procurement_headers, project_id)
    assert len(project["vendors"]) >= 2
    vendor_id = project["vendors"][1]["id"]

    review_response = client.post(
        f"/projects/{project_id}/vendors/{vendor_id}/review",
        headers=procurement_headers,
        json={
            "query": "请判断这家公司是否适合作为供应商，并给出风险点。",
            "top_k": 5,
        },
    )
    assert review_response.status_code == 200, review_response.text
    review_payload = review_response.json()
    assert review_payload["vendor"]["ai_review_trace_id"]
    assert review_payload["project"]["current_stage"] == "procurement_sourcing"
    assert review_payload["assessment"]["review_kind"] == "vendor_onboarding"
    assert review_payload["assessment"]["check_items"]
    assert review_payload["vendor"]["structured_review"]["review_kind"] == "vendor_onboarding"

    project = complete_current_stage(client, procurement_headers, get_project(client, procurement_headers, project_id))
    select_response = client.post(
        f"/projects/{project_id}/vendors/{vendor_id}/select",
        headers=procurement_headers,
        json={"reason": "综合比选后最优"},
    )
    assert select_response.status_code == 200, select_response.text
    project = select_response.json()
    assert project["current_stage"] == "legal_review"
    assert project["selected_vendor_id"] == vendor_id

    blocked_legal_review = client.post(
        f"/projects/{project_id}/legal/review",
        headers=legal_headers,
        json={
            "query": "请对比合同并给出合法合规风险。",
            "top_k": 5,
        },
    )
    assert blocked_legal_review.status_code == 400

    project = get_project(client, legal_headers, project_id)
    for artifact in project["artifacts"]:
        if artifact["stage"] != "legal_review":
            continue
        response = client.patch(
            f"/projects/{project_id}/artifacts/{artifact['id']}",
            headers=legal_headers,
            json={"status": "provided"},
        )
        assert response.status_code == 200, response.text

    legal_review = client.post(
        f"/projects/{project_id}/legal/review",
        headers=legal_headers,
        json={
            "query": "请对比我方合同和对方红线版本，给出合法合规判断。",
            "top_k": 5,
        },
    )
    assert legal_review.status_code == 200, legal_review.text
    assert legal_review.json()["review"]["trace_id"]

    returned = client.post(
        f"/projects/{project_id}/return-to-procurement",
        headers=legal_headers,
        json={"reason": "合同核心条款被弱化"},
    )
    assert returned.status_code == 200, returned.text

    project = get_project(client, procurement_headers, project_id)
    assert project["current_stage"] == "procurement_sourcing"
    assert project["selected_vendor_id"] == ""
    rejected_vendor = next(vendor for vendor in project["vendors"] if vendor["id"] == vendor_id)
    assert rejected_vendor["status"] == "legal_rejected"


def test_procurement_agent_review_can_assess_unsaved_vendor_draft(client, auth_headers):
    project, _business_headers, _manager_headers, procurement_headers = reach_procurement_stage(client, auth_headers)
    project_id = project["id"]

    review_response = client.post(
        f"/projects/{project_id}/procurement-agent-review",
        headers=procurement_headers,
        json={
            "vendor_name": "DataBridge Cloud",
            "source_platform": "官网",
            "source_url": "https://example.com/databridge",
            "profile_summary": "提供客服数据分析与工单协同能力，支持 SaaS 方式接入。",
            "procurement_notes": "已线下比较服务能力和报价，准备先做准入判断再决定是否绑定。",
            "focus_points": "重点关注是否涉及客户数据处理以及还缺哪些准入材料。",
            "top_k": 5,
        },
    )
    assert review_response.status_code == 200, review_response.text
    payload = review_response.json()
    assert payload["review"]["trace_id"]
    assert payload["assessment"]["review_kind"] == "procurement_agent_review"
    assert payload["assessment"]["check_items"]
    assert "供应商名称" in payload["generated_query"]


def test_procurement_material_upload_can_extract_vendor_draft(client, auth_headers):
    project, _business_headers, _manager_headers, procurement_headers = reach_procurement_stage(client, auth_headers)
    project_id = project["id"]

    extract_response = client.post(
        f"/projects/{project_id}/procurement-agent-extract",
        headers=procurement_headers,
        files=[
            (
                "files",
                (
                    "vendor_profile.md",
                    "# 供应商名称：DataBridge Cloud\n\nDataBridge Cloud 提供客服数据分析、工单协同与报表能力，适合 SaaS 交付。\n官网：https://vendors.example.com/databridge\n",
                    "text/markdown",
                ),
            ),
            (
                "files",
                (
                    "vendor_quote.txt",
                    "本次报价覆盖 120 个坐席和报表模块，支持客户数据处理与接口对接。建议采购先完成准入审查。",
                    "text/plain",
                ),
            ),
        ],
    )
    assert extract_response.status_code == 200, extract_response.text
    payload = extract_response.json()
    assert payload["vendor_draft"]["vendor_name"] == "DataBridge Cloud"
    assert payload["vendor_draft"]["source_url"] == "https://vendors.example.com/databridge"
    assert payload["vendor_draft"]["profile_summary"]
    assert len(payload["extracted_materials"]) == 2


def test_final_approval_signing_and_archive_snapshot(client, auth_headers):
    project, _business_headers, manager_headers, procurement_headers = reach_procurement_stage(client, auth_headers)
    legal_headers = auth_headers("legal")
    admin_headers = auth_headers("admin")
    project_id = project["id"]
    vendor_id = project["vendors"][0]["id"]

    project = complete_current_stage(client, procurement_headers, project)
    select_response = client.post(
        f"/projects/{project_id}/vendors/{vendor_id}/select",
        headers=procurement_headers,
        json={"reason": "进入法务"},
    )
    assert select_response.status_code == 200, select_response.text

    project = complete_current_stage(client, legal_headers, select_response.json())
    legal_approve = client.post(
        f"/projects/{project_id}/legal-decision",
        headers=legal_headers,
        json={"decision": "approve", "reason": "条款可接受"},
    )
    assert legal_approve.status_code == 200, legal_approve.text

    project = legal_approve.json()
    assert project["current_stage"] == "final_approval"
    assert project["blocker_summary"] == []
    final_approve = client.post(
        f"/projects/{project_id}/final-approve",
        headers=manager_headers,
        json={"reason": "批准落地"},
    )
    assert final_approve.status_code == 200, final_approve.text

    project = complete_current_stage(client, admin_headers, get_project(client, admin_headers, project_id))
    sign_response = client.post(
        f"/projects/{project_id}/sign",
        headers=admin_headers,
        json={"reason": "完成签署"},
    )
    assert sign_response.status_code == 200, sign_response.text
    project = sign_response.json()
    assert project["current_stage"] == "completed"
    assert project["status"] == "completed"
    assert project["archives"]

    timeline = client.get(f"/projects/{project_id}/timeline", headers=admin_headers)
    assert timeline.status_code == 200, timeline.text
    items = timeline.json()
    assert any(item["kind"] == "archive" for item in items)


def test_final_return_and_cancel_flow(client, auth_headers):
    project, _business_headers, manager_headers, procurement_headers = reach_procurement_stage(client, auth_headers)
    legal_headers = auth_headers("legal")
    project_id = project["id"]
    vendor_id = project["vendors"][0]["id"]

    project = complete_current_stage(client, procurement_headers, project)
    select_response = client.post(
        f"/projects/{project_id}/vendors/{vendor_id}/select",
        headers=procurement_headers,
        json={"reason": "进入法务"},
    )
    assert select_response.status_code == 200, select_response.text

    project = complete_current_stage(client, legal_headers, select_response.json())
    legal_review = client.post(
        f"/projects/{project_id}/legal/review",
        headers=legal_headers,
        json={
            "query": "请对比我方合同和对方红线版本，给出合法合规判断。",
            "top_k": 5,
        },
    )
    assert legal_review.status_code == 200, legal_review.text
    assert legal_review.json()["assessment"]["review_kind"] == "legal_contract_review"

    legal_approve = client.post(
        f"/projects/{project_id}/legal-decision",
        headers=legal_headers,
        json={"decision": "approve", "reason": "条款可接受"},
    )
    assert legal_approve.status_code == 200, legal_approve.text
    project = complete_current_stage(client, manager_headers, legal_approve.json())
    assert project["latest_legal_review"]["review_kind"] == "legal_contract_review"

    final_return = client.post(
        f"/projects/{project_id}/final-return",
        headers=manager_headers,
        json={"target_stage": "legal_review", "reason": "需要法务补充说明"},
    )
    assert final_return.status_code == 200, final_return.text
    project = final_return.json()
    assert project["current_stage"] == "legal_review"
    assert project["selected_vendor_id"] == vendor_id

    cancel_response = client.post(
        f"/projects/{project_id}/cancel",
        headers=legal_headers,
        json={"reason": "项目预算冻结，取消"},
    )
    assert cancel_response.status_code == 200, cancel_response.text
    cancelled_project = cancel_response.json()
    assert cancelled_project["status"] == "cancelled"
    assert cancelled_project["allowed_actions"] == []
