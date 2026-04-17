from __future__ import annotations

from sqlalchemy import delete


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
    assert project["legal_handoff"]["our_contract_status"] == "missing"
    assert project["legal_handoff"]["counterparty_contract_status"] == "missing"

    blocked_legal_review = client.post(
        f"/projects/{project_id}/legal/review",
        headers=legal_headers,
        json={"top_k": 5},
    )
    assert blocked_legal_review.status_code == 400
    assert "我方采购合同" in blocked_legal_review.text

    project = get_project(client, legal_headers, project_id)
    legal_artifacts = [artifact for artifact in project["artifacts"] if artifact["stage"] == "legal_review"]
    our_contract = next(artifact for artifact in legal_artifacts if artifact["artifact_type"] == "our_procurement_contract")
    redline_contract = next(
        artifact for artifact in legal_artifacts if artifact["artifact_type"] == "counterparty_redline_contract"
    )
    first_upload = client.post(
        f"/projects/{project_id}/artifacts/{our_contract['id']}/upload",
        headers=legal_headers,
        files={"file": ("our-procurement-contract.md", b"# Our Contract\n\nLiability cap is 12 months.\n", "text/markdown")},
    )
    assert first_upload.status_code == 200, first_upload.text
    first_upload_payload = first_upload.json()
    assert first_upload_payload["status"] == "provided"
    assert first_upload_payload["document_id"]
    assert "our-procurement-contract.md" in first_upload_payload["notes"]
    preview_response = client.get(
        f"/projects/{project_id}/artifacts/{our_contract['id']}/preview",
        headers=legal_headers,
    )
    assert preview_response.status_code == 200, preview_response.text
    assert "Liability cap is 12 months" in preview_response.json()["text_content"]

    blocked_legal_review = client.post(
        f"/projects/{project_id}/legal/review",
        headers=legal_headers,
        json={"top_k": 5},
    )
    assert blocked_legal_review.status_code == 400
    assert "对方修改后的采购合同" in blocked_legal_review.text

    second_upload = client.post(
        f"/projects/{project_id}/artifacts/{redline_contract['id']}/upload",
        headers=legal_headers,
        files={
            "file": (
                "counterparty-redline-contract.md",
                b"# Counterparty Redline\n\nLiability cap is limited to 3 months and audit rights are removed.\n",
                "text/markdown",
            )
        },
    )
    assert second_upload.status_code == 200, second_upload.text
    second_upload_payload = second_upload.json()
    assert second_upload_payload["status"] == "provided"
    assert second_upload_payload["document_id"]
    assert "counterparty-redline-contract.md" in second_upload_payload["notes"]
    redline_preview = client.get(
        f"/projects/{project_id}/artifacts/{redline_contract['id']}/preview",
        headers=legal_headers,
    )
    assert redline_preview.status_code == 200, redline_preview.text
    assert "audit rights are removed" in redline_preview.json()["text_content"]

    refreshed_project = get_project(client, legal_headers, project_id)
    refreshed_our_contract = next(
        artifact for artifact in refreshed_project["artifacts"] if artifact["id"] == our_contract["id"]
    )
    refreshed_redline_contract = next(
        artifact for artifact in refreshed_project["artifacts"] if artifact["id"] == redline_contract["id"]
    )
    assert refreshed_our_contract["document_id"]
    assert refreshed_redline_contract["document_id"]

    for artifact in refreshed_project["artifacts"]:
        if artifact["stage"] != "legal_review" or artifact["id"] in {our_contract["id"], redline_contract["id"]}:
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
        json={"top_k": 5},
    )
    assert legal_review.status_code == 200, legal_review.text
    legal_payload = legal_review.json()
    assert legal_payload["review"]["trace_id"]
    assert legal_payload["assessment"]["review_kind"] == "legal_contract_review"
    assert legal_payload["assessment"]["risk_level"] in {"low", "medium", "high"}
    assert legal_payload["assessment"]["decision_suggestion"] in {"approve", "return"}
    assert "clause_gaps" in legal_payload["assessment"]
    assert "evidence" in legal_payload["assessment"]
    assert legal_payload["project"]["latest_legal_review"]["review_kind"] == "legal_contract_review"

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


def test_legal_detail_self_heals_missing_contract_artifacts(client, auth_headers):
    project, _business_headers, _manager_headers, procurement_headers = reach_procurement_stage(client, auth_headers)
    legal_headers = auth_headers("legal")
    project_id = project["id"]

    create_vendor_response = client.post(
        f"/projects/{project_id}/vendors",
        headers=procurement_headers,
        json={
            "vendor_name": "晨帆协作软件有限公司",
            "source_platform": "官网",
            "source_url": "https://example.com/morning-sail",
            "profile_summary": "团队协作软件服务商。",
            "procurement_notes": "用于模拟旧项目进入法务后缺失合同卡片的场景。",
        },
    )
    assert create_vendor_response.status_code == 200, create_vendor_response.text

    project = get_project(client, procurement_headers, project_id)
    vendor_id = project["vendors"][-1]["id"]

    review_response = client.post(
        f"/projects/{project_id}/vendors/{vendor_id}/review",
        headers=procurement_headers,
        json={"query": "请完成一轮供应商审查。", "top_k": 5},
    )
    assert review_response.status_code == 200, review_response.text

    select_response = client.post(
        f"/projects/{project_id}/vendors/{vendor_id}/select",
        headers=procurement_headers,
        json={"reason": "进入法务审核。"},
    )
    assert select_response.status_code == 200, select_response.text

    with client.app.state.container.session_factory() as db:
        from app.models.entities import ProcurementStage, ProjectArtifact

        db.execute(
            delete(ProjectArtifact).where(
                ProjectArtifact.project_id == project_id,
                ProjectArtifact.stage == ProcurementStage.legal_review.value,
                ProjectArtifact.artifact_type.in_(["our_procurement_contract", "counterparty_redline_contract"]),
            )
        )
        db.commit()

    healed_project = get_project(client, legal_headers, project_id)
    legal_artifacts = [artifact for artifact in healed_project["artifacts"] if artifact["stage"] == "legal_review"]
    artifact_types = {artifact["artifact_type"] for artifact in legal_artifacts}
    assert "our_procurement_contract" in artifact_types
    assert "counterparty_redline_contract" in artifact_types
    healed_our_contract = next(artifact for artifact in legal_artifacts if artifact["artifact_type"] == "our_procurement_contract")

    upload_response = client.post(
        f"/projects/{project_id}/artifacts/{healed_our_contract['id']}/upload",
        headers=legal_headers,
        files={"file": ("healed-our-contract.md", b"# Healed Contract\n\nThis upload should succeed.\n", "text/markdown")},
    )
    assert upload_response.status_code == 200, upload_response.text


def test_legal_handoff_prefers_uploaded_contract_over_legacy_missing_artifact(client, auth_headers):
    project, _business_headers, _manager_headers, procurement_headers = reach_procurement_stage(client, auth_headers)
    legal_headers = auth_headers("legal")
    project_id = project["id"]

    project = get_project(client, procurement_headers, project_id)
    vendor_id = project["vendors"][0]["id"]

    review_response = client.post(
        f"/projects/{project_id}/vendors/{vendor_id}/review",
        headers=procurement_headers,
        json={"query": "请完成一轮供应商审查。", "top_k": 5},
    )
    assert review_response.status_code == 200, review_response.text

    select_response = client.post(
        f"/projects/{project_id}/vendors/{vendor_id}/select",
        headers=procurement_headers,
        json={"reason": "进入法务审核。"},
    )
    assert select_response.status_code == 200, select_response.text

    with client.app.state.container.session_factory() as db:
        from app.models.entities import ProcurementStage, ProjectArtifact

        db.add(
            ProjectArtifact(
                project_id=project_id,
                stage=ProcurementStage.legal_review.value,
                artifact_type="standard_contract_dispatch",
                title="旧版我方合同",
                required=True,
                document_id="",
                linked_vendor_id=vendor_id,
                direction="internal",
                version_no=1,
                status="missing",
                notes="legacy missing artifact",
            )
        )
        db.commit()

    project = get_project(client, legal_headers, project_id)
    our_contract = next(
        artifact for artifact in project["artifacts"] if artifact["stage"] == "legal_review" and artifact["artifact_type"] == "our_procurement_contract"
    )
    upload_response = client.post(
        f"/projects/{project_id}/artifacts/{our_contract['id']}/upload",
        headers=legal_headers,
        files={"file": ("our-procurement-contract.md", b"# Our Contract\n\nUploaded latest contract.\n", "text/markdown")},
    )
    assert upload_response.status_code == 200, upload_response.text

    refreshed = get_project(client, legal_headers, project_id)
    assert refreshed["legal_handoff"]["our_contract_status"] == "provided"
    assert "法务审查缺少我方采购合同" not in refreshed["blocker_summary"]


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
    assert payload["review"]["tool_calls"]
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


def test_legal_approval_moves_directly_to_signing_and_archive_snapshot(client, auth_headers):
    project, _business_headers, _manager_headers, procurement_headers = reach_procurement_stage(client, auth_headers)
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
    assert project["current_stage"] == "signing"
    assert any("签署" in item or "归档" in item for item in project["blocker_summary"])

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


def test_signing_cancel_flow_preserves_latest_legal_review(client, auth_headers):
    project, _business_headers, _manager_headers, procurement_headers = reach_procurement_stage(client, auth_headers)
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
    legal_review = client.post(
        f"/projects/{project_id}/legal/review",
        headers=legal_headers,
        json={"top_k": 5},
    )
    assert legal_review.status_code == 200, legal_review.text
    assert legal_review.json()["assessment"]["review_kind"] == "legal_contract_review"
    assert legal_review.json()["assessment"]["risk_level"] in {"low", "medium", "high"}
    assert legal_review.json()["assessment"]["decision_suggestion"] in {"approve", "return"}

    legal_approve = client.post(
        f"/projects/{project_id}/legal-decision",
        headers=legal_headers,
        json={"decision": "approve", "reason": "条款可接受"},
    )
    assert legal_approve.status_code == 200, legal_approve.text
    project = complete_current_stage(client, admin_headers, legal_approve.json())
    assert project["latest_legal_review"]["review_kind"] == "legal_contract_review"
    assert project["latest_legal_review"]["decision_suggestion"] in {"approve", "return"}
    assert project["current_stage"] == "signing"
    assert project["selected_vendor_id"] == vendor_id

    cancel_response = client.post(
        f"/projects/{project_id}/cancel",
        headers=admin_headers,
        json={"reason": "项目预算冻结，取消"},
    )
    assert cancel_response.status_code == 200, cancel_response.text
    cancelled_project = cancel_response.json()
    assert cancelled_project["status"] == "cancelled"
    assert cancelled_project["allowed_actions"] == []
