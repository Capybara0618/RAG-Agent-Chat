from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import build_settings
from app.main import create_app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
        sample_files = [
            (
                "procurement_cn_vendor_onboarding_policy.md",
                "# 供应商准入与尽职调查管理办法\n\n## 基础准入材料\n新供应商准入前，采购经理必须收集营业执照、法定代表人信息、银行账户证明、税务登记信息以及最近一期审计报告。\n\n## 高风险供应商增强尽调\n若供应商将接触公司客户数据、生产环境或核心源代码，除基础材料外，还必须完成信息安全问卷、数据处理说明、过往安全事件披露以及法务与信息安全双重审批。\n".encode(
                    "utf-8"
                ),
            ),
            (
                "procurement_cn_contract_playbook.md",
                "# 采购合同审查红线指引\n\n## 核心红线条款\n标准合同模板中必须保留以下条款：责任上限、赔偿条款、审计权、数据处理、分包限制、安全事件通知和便利终止。\n\n## 审计权\n对处理公司敏感数据或关键业务流程的供应商，合同中必须保留合理范围内的审计权。\n".encode(
                    "utf-8"
                ),
            ),
            (
                "procurement_cn_standard_msa_template.md",
                "# 标准主服务协议模板\n\n## Liability Cap\nSupplier's aggregate liability shall not exceed twelve months of fees paid under this agreement, except for confidentiality breach, data protection violation, and gross negligence.\n\n## Audit Rights\nCustomer may conduct one audit per contract year upon reasonable notice where supplier processes sensitive customer data.\n\n## Security Incident Notification\nSupplier must notify customer of a confirmed security incident within 24 hours.\n\n## Termination for Convenience\nCustomer may terminate the agreement for convenience with 30 days written notice.\n".encode(
                    "utf-8"
                ),
            ),
            (
                "procurement_cn_vendor_redline_msa.md",
                "# 供应商回传主服务协议红线版本\n\n## Liability Cap\nSupplier's liability shall be limited to three months of fees paid under the agreement.\n\n## Data Processing\nSupplier may engage subprocessors upon notice and may transfer service data to affiliated hosting locations as needed for operations.\n\n## Payment Terms\nCustomer shall pay all undisputed invoices within 45 days after receipt.\n".encode(
                    "utf-8"
                ),
            ),
            (
                "procurement_cn_security_review_sop.md",
                "# 供应商安全评审SOP\n\n## 第一步\n供应商涉及系统接入、数据处理或 SaaS 服务采购时，第一步是创建安全评审工单，并附上问卷、产品架构图和数据流说明。\n".encode(
                    "utf-8"
                ),
            ),
            (
                "procurement_cn_approval_matrix.md",
                "# 采购审批矩阵\n\n## 法务升级审批\n出现以下任一情况时，必须升级法务审批：删除或弱化责任上限、删除审计权、涉及个人信息或跨境数据处理、供应商要求修改赔偿范围或争议解决条款。\n".encode(
                    "utf-8"
                ),
            ),
            (
                "procurement_cn_faq.csv",
                "question,answer\n供应商准入前必须收集哪些基础材料?,需要收集营业执照、法定代表人信息、银行账户证明、税务登记信息和最近一期审计报告。\n哪些情况必须升级法务审批?,删除或弱化责任上限、删除审计权、涉及个人信息或跨境数据处理等情况必须升级法务审批。\n".encode(
                    "utf-8"
                ),
            ),
        ]
        for name, content in sample_files:
            response = test_client.post(
                "/knowledge/upload",
                files={"file": (name, content, "application/octet-stream")},
                data={"allowed_roles": "employee", "tags": "sample"},
            )
            assert response.status_code == 200, response.text
            task_id = response.json()["task_id"]
            task_response = test_client.get(f"/knowledge/tasks/{task_id}")
            assert task_response.status_code == 200, task_response.text
            assert task_response.json()["status"] == "indexed"
        yield test_client
