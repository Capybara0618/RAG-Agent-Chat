from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import build_settings
from app.main import create_app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def login_headers(client: TestClient, username: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": username, "password": username})
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    database_url = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    storage_dir = tmp_path / "uploads"
    settings = build_settings(
        database_url=database_url,
        storage_dir=str(storage_dir),
        api_base_url="http://testserver",
    )
    app = create_app(settings)

    with TestClient(app) as test_client:
        admin_headers = login_headers(test_client, "admin")
        sample_files = [
            (
                "采购核心-供应商准入办法.md",
                "# 供应商准入办法\n\n## 基础准入材料\n至少需要主体信息、公开来源、产品或服务说明、商务材料和联系人信息。\n\n## 不得进入正式审查的情形\n无法确认主体身份、无法确认来源、无法确认产品能力，或材料与供应商准入无关时，不得进入正式审查。\n".encode("utf-8"),
            ),
            (
                "法务核心-合同审查红线指引.md",
                "# 合同审查红线指引\n\n## 核心红线\n责任上限、赔偿责任、审计权、数据处理、安全事件通知和便利终止条款原则上不得删除或明显弱化。\n".encode("utf-8"),
            ),
            (
                "法务核心-标准主服务协议模板.md",
                "# 标准主服务协议模板\n\n## 责任上限\n责任上限原则上不低于过去十二个月服务费总额。\n\n## 审计权\n如处理敏感数据，我方有权在合理通知后开展审计。\n\n## 安全事件通知\n发生已确认的安全事件后，供应商应在二十四小时内通知我方。\n".encode("utf-8"),
            ),
            (
                "法务核心-供应商回传红线协议.md",
                "# 供应商回传红线协议\n\n## 责任上限\n供应商责任上限调整为不超过三个月服务费总额。\n\n## 数据处理\n供应商可在通知后自行安排分包处理。\n\n## 安全事件通知\n供应商不承诺固定通知时限。\n".encode("utf-8"),
            ),
            (
                "采购核心-安全评审操作流程.md",
                "# 安全评审操作流程\n\n## 第一步\n第一步是创建安全评审记录，并要求供应商补充安全能力说明、架构图和数据流说明。\n".encode("utf-8"),
            ),
            (
                "采购核心-采购审批矩阵.md",
                "# 采购审批矩阵\n\n## 法务升级条件\n删除或弱化责任上限、删除审计权、修改赔偿责任或争议解决条款时，必须升级法务审批。\n".encode("utf-8"),
            ),
            (
                "采购核心-常见问答.csv",
                "问题,回答\n供应商准入前至少要收集哪些基础材料？,至少要收集主体信息、公开来源、产品或服务说明、商务材料和联系人信息。\n哪些情况必须升级法务审批？,删除或弱化责任上限、删除审计权、修改赔偿责任或争议解决条款等情况必须升级法务审批。\n".encode("utf-8"),
            ),
        ]
        for name, content in sample_files:
            response = test_client.post(
                "/knowledge/upload",
                files={"file": (name, content, "application/octet-stream")},
                data={"allowed_roles": "employee", "tags": "sample"},
                headers=admin_headers,
            )
            assert response.status_code == 200, response.text
            task_id = response.json()["task_id"]
            task_response = test_client.get(f"/knowledge/tasks/{task_id}", headers=admin_headers)
            assert task_response.status_code == 200, task_response.text
            assert task_response.json()["status"] == "indexed"
        yield test_client


@pytest.fixture()
def auth_headers(client: TestClient):
    def _login(username: str) -> dict[str, str]:
        return login_headers(client, username)

    return _login
