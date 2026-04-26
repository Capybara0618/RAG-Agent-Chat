from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import build_settings
from app.main import create_app


RUNTIME_ROOT = Path("tmp_eval_legal_smoke")

LEGAL_KB_FILES = [
    (
        "法务核心-合同审查红线指引.md",
        """# 合同审查红线指引

## 核心红线
责任上限、赔偿责任、审计权、数据处理、保密义务、安全事件通知原则上不得删除或明显弱化。

## 处理要求
若对方坚持删除或弱化核心条款，应退回采购重新沟通，并由法务人工确认是否接受偏离。
""",
    ),
    (
        "法务核心-标准主服务协议模板.md",
        """# 标准主服务协议模板

## 责任上限
供应商在本协议项下的累计责任上限原则上不低于过去十二个月已收取服务费总额。

## 审计权
如供应商处理我方业务数据，我方有权在合理通知后开展审计或要求提供审计证明。

## 数据处理
供应商仅可根据我方书面指示处理数据，未经同意不得跨境传输，不得擅自变更处理目的。

## 安全事件通知
发生已确认的安全事件后，供应商应在二十四小时内通知我方。

## 保密义务
供应商对我方保密信息负有持续保密义务，未经书面许可不得向第三方披露。
""",
    ),
    (
        "法务核心-数据处理供应商检查清单.md",
        """# 数据处理供应商检查清单

## 高风险信号
出现以下任一情形时，应视为重点风险并升级法务复核：
1. 允许供应商按运营需要自行跨境传输数据。
2. 允许供应商自行安排分包或子处理且无需我方书面同意。
3. 不承诺固定的安全事件通知时限。
""",
    ),
    (
        "法务核心-争议解决补充说明.md",
        """# 争议解决补充说明

## 常见关注点
若对方要求适用境外法律、境外仲裁地或由供应商所在地法院专属管辖，应视为法务观察项并结合项目重要性判断是否接受。
""",
    ),
]

SCENARIOS = [
    {
        "name": "severe_redline",
        "expected_decision": "return",
        "expected_risk": "high",
        "our_contract_name": "我方采购合同（标准版）.md",
        "counterparty_contract_name": "对方回传合同?.md",
        "our_contract": """# 我方采购合同

## 核心条款
责任上限原则上不低于过去十二个月已收取服务费总额。
供应商应承担赔偿责任。
我方保留审计权。
供应商仅可根据我方书面指示处理数据，未经同意不得跨境传输。
发生安全事件后，供应商应在二十四小时内通知我方。
供应商对我方保密信息负有持续保密义务。
""",
        "counterparty_contract": """# 对方修改后的采购合同

## 核心条款
责任上限调整为不超过三个月服务费总额。
供应商仅退还已收费用，不承担其他赔偿责任。
供应商可根据运营需要将服务数据传输至其关联部署地点，并可自行安排分包。
发生安全事件后，供应商将在合理可行范围内尽快通知，但不承诺固定通知时限。
供应商可向合作方披露业务信息用于服务运营。
""",
    },
    {
        "name": "mostly_clean_with_watch_item",
        "expected_decision": "approve",
        "expected_risk": "medium",
        "our_contract_name": "我方采购合同（标准版）.md",
        "counterparty_contract_name": "对方回传合同（轻微修改）.md",
        "our_contract": """# 我方采购合同

## 核心条款
责任上限原则上不低于过去十二个月已收取服务费总额。
我方保留审计权。
供应商仅可根据我方书面指示处理数据。
发生安全事件后，供应商应在二十四小时内通知我方。
供应商对我方保密信息负有持续保密义务。
争议解决适用中华人民共和国法律，由我方所在地法院管辖。
付款期限为验收后三十日。
""",
        "counterparty_contract": """# 对方修改后的采购合同

## 核心条款
责任上限原则上不低于过去十二个月已收取服务费总额。
我方保留审计权。
供应商仅可根据我方书面指示处理数据。
发生安全事件后，供应商应在二十四小时内通知我方。
供应商对我方保密信息负有持续保密义务。
争议解决适用中华人民共和国法律，由供应商所在地法院管辖。
付款期限为验收后四十五日。
""",
    },
    {
        "name": "data_processing_risk",
        "expected_decision": "return",
        "expected_risk": "high",
        "our_contract_name": "我方采购合同（标准版）.md",
        "counterparty_contract_name": "供应商数据处理回传版*.md",
        "our_contract": """# 我方采购合同

## 数据与安全条款
供应商仅可根据我方书面指示处理数据，未经同意不得跨境传输。
发生安全事件后，供应商应在二十四小时内通知我方。
我方保留审计权。
""",
        "counterparty_contract": """# 对方修改后的采购合同

## 数据与安全条款
供应商可根据运营需要将服务数据传输至境外关联部署地点。
供应商可自行安排子处理方提供服务，无需逐次取得我方书面同意。
发生安全事件后，供应商将在合理可行范围内尽快通知。
""",
    },
]


def login_headers(client: TestClient, username: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": username, "password": username})
    response.raise_for_status()
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def create_runtime_dir() -> Path:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    runtime_dir = RUNTIME_ROOT / f"run_{os.getpid()}"
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir, ignore_errors=True)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def create_runtime_client(runtime_dir: Path) -> TestClient:
    settings = build_settings(
        database_url=f"sqlite:///{(runtime_dir / 'legal_smoke.db').resolve().as_posix()}",
        storage_dir=str((runtime_dir / "uploads").resolve()),
        api_base_url="http://testserver",
        embedding_model="",
        reranker_enabled=False,
    )
    app = create_app(settings)
    return TestClient(app)


def upload_knowledge_base(client: TestClient, admin_headers: dict[str, str]) -> None:
    print(f"[legal-smoke] upload kb docs={len(LEGAL_KB_FILES)}")
    for index, (name, content) in enumerate(LEGAL_KB_FILES, start=1):
        response = client.post(
            "/knowledge/upload",
            headers=admin_headers,
            files={"file": (name, content.encode("utf-8"), "text/markdown")},
            data={"allowed_roles": "employee", "tags": "sample,legal"},
        )
        response.raise_for_status()
        task_id = response.json()["task_id"]
        task = client.get(f"/knowledge/tasks/{task_id}", headers=admin_headers)
        task.raise_for_status()
        print(f"[legal-smoke] kb progress={index}/{len(LEGAL_KB_FILES)} status={task.json()['status']} title={name}")


def create_project(client: TestClient, business_headers: dict[str, str]) -> dict[str, object]:
    payload = {
        "title": "客服系统采购合同审查",
        "requester_name": "王悦",
        "department": "客户服务部",
        "vendor_name": "云服科技",
        "category": "customer-support-saas",
        "budget_amount": 580000,
        "currency": "CNY",
        "summary": "采购客服 SaaS，法务需要审核对方回传合同。",
        "business_value": "统一客服流程并降低响应时长。",
        "target_go_live_date": "2026-06-30",
        "data_scope": "customer_data",
    }
    response = client.post("/projects", headers=business_headers, json=payload)
    response.raise_for_status()
    return response.json()


def get_project(client: TestClient, headers: dict[str, str], project_id: str) -> dict[str, object]:
    response = client.get(f"/projects/{project_id}", headers=headers)
    response.raise_for_status()
    return response.json()


def complete_stage(client: TestClient, headers: dict[str, str], project: dict[str, object]) -> dict[str, object]:
    project_id = str(project["id"])
    current_stage = str(project["current_stage"])
    for task in project["tasks"]:
        if task["stage"] != current_stage or task["status"] == "done":
            continue
        response = client.patch(
            f"/projects/{project_id}/tasks/{task['id']}",
            headers=headers,
            json={"status": "done"},
        )
        response.raise_for_status()
    for artifact in project["artifacts"]:
        if artifact["stage"] != current_stage or artifact["status"] in {"provided", "approved"}:
            continue
        response = client.patch(
            f"/projects/{project_id}/artifacts/{artifact['id']}",
            headers=headers,
            json={"status": "provided"},
        )
        response.raise_for_status()
    return get_project(client, headers, project_id)


def reach_legal_stage(
    client: TestClient,
    business_headers: dict[str, str],
    manager_headers: dict[str, str],
    procurement_headers: dict[str, str],
) -> dict[str, object]:
    project = create_project(client, business_headers)
    project_id = str(project["id"])
    submit_response = client.post(f"/projects/{project_id}/submit", headers=business_headers, json={"reason": ""})
    submit_response.raise_for_status()
    approve_response = client.post(
        f"/projects/{project_id}/manager-decision",
        headers=manager_headers,
        json={"decision": "approve", "reason": "进入采购阶段"},
    )
    approve_response.raise_for_status()
    project = approve_response.json()
    project = complete_stage(client, procurement_headers, project)
    vendor_id = str(project["vendors"][0]["id"])
    select_response = client.post(
        f"/projects/{project_id}/vendors/{vendor_id}/select",
        headers=procurement_headers,
        json={"reason": "进入法务合同审查"},
    )
    select_response.raise_for_status()
    return select_response.json()


def upload_legal_contracts(
    client: TestClient,
    legal_headers: dict[str, str],
    project: dict[str, object],
    scenario: dict[str, str],
) -> dict[str, object]:
    project_id = str(project["id"])
    legal_artifacts = [artifact for artifact in project["artifacts"] if artifact["stage"] == "legal_review"]
    our_contract = next(artifact for artifact in legal_artifacts if artifact["artifact_type"] == "our_procurement_contract")
    counterparty_contract = next(
        artifact for artifact in legal_artifacts if artifact["artifact_type"] == "counterparty_redline_contract"
    )
    for artifact, field_name, content_name in (
        (our_contract, "our_contract", "our_contract_name"),
        (counterparty_contract, "counterparty_contract", "counterparty_contract_name"),
    ):
        response = client.post(
            f"/projects/{project_id}/artifacts/{artifact['id']}/upload",
            headers=legal_headers,
            files={"file": (scenario[content_name], scenario[field_name].encode("utf-8"), "text/markdown")},
        )
        response.raise_for_status()
    refreshed = get_project(client, legal_headers, project_id)
    for artifact in refreshed["artifacts"]:
        if artifact["stage"] != "legal_review" or artifact["status"] in {"provided", "approved"}:
            continue
        response = client.patch(
            f"/projects/{project_id}/artifacts/{artifact['id']}",
            headers=legal_headers,
            json={"status": "provided"},
        )
        response.raise_for_status()
    return get_project(client, legal_headers, project_id)


def run_scenario(
    client: TestClient,
    headers: dict[str, dict[str, str]],
    scenario: dict[str, str],
) -> dict[str, object]:
    print(f"[legal-smoke] scenario={scenario['name']} start")
    project = reach_legal_stage(
        client,
        headers["business"],
        headers["manager"],
        headers["procurement"],
    )
    project = upload_legal_contracts(client, headers["legal"], project, scenario)
    project_id = str(project["id"])
    review_response = client.post(
        f"/projects/{project_id}/legal/review",
        headers=headers["legal"],
        json={"top_k": 5},
    )
    review_response.raise_for_status()
    payload = review_response.json()
    assessment = payload["assessment"]
    debug_summary = payload["review"].get("debug_summary", {})
    comparison_view = debug_summary.get("comparison_view", {})
    result = {
        "scenario": scenario["name"],
        "expected_decision": scenario["expected_decision"],
        "actual_decision": assessment["decision_suggestion"],
        "expected_risk": scenario["expected_risk"],
        "actual_risk": assessment["risk_level"],
        "pass": assessment["decision_suggestion"] == scenario["expected_decision"]
        and assessment["risk_level"] == scenario["expected_risk"],
        "clause_gaps": assessment.get("clause_gaps", []),
        "risk_flags": assessment.get("risk_flags", []),
        "open_questions": assessment.get("open_questions", []),
        "citations": [item["document_title"] for item in assessment.get("evidence", [])],
        "comparison_view": comparison_view,
        "summary": assessment.get("summary", ""),
    }
    print(
        "[legal-smoke] "
        f"scenario={scenario['name']} decision={result['actual_decision']} risk={result['actual_risk']} "
        f"citations={len(result['citations'])} pass={result['pass']}"
    )
    return result


def main() -> None:
    runtime_dir = create_runtime_dir()
    with create_runtime_client(runtime_dir) as client:
        headers = {
            "admin": login_headers(client, "admin"),
            "business": login_headers(client, "business"),
            "manager": login_headers(client, "manager"),
            "procurement": login_headers(client, "procurement"),
            "legal": login_headers(client, "legal"),
        }
        upload_knowledge_base(client, headers["admin"])
        results = [run_scenario(client, headers, scenario) for scenario in SCENARIOS]

    summary = {
        "scenario_count": len(results),
        "passed": sum(1 for item in results if item["pass"]),
        "result_file": str((runtime_dir / "legal_smoke_result.json").resolve()),
        "results": results,
    }
    result_path = runtime_dir / "legal_smoke_result.json"
    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[legal-smoke] summary")
    print(f"  scenarios={summary['scenario_count']} passed={summary['passed']}")
    print(f"  result_file={result_path.resolve()}")
    for item in results:
        print(
            "  "
            f"{item['scenario']}: decision={item['actual_decision']} risk={item['actual_risk']} "
            f"pass={item['pass']}"
        )


if __name__ == "__main__":
    main()
