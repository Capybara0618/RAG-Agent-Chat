from __future__ import annotations


def test_business_cannot_access_admin_knowledge_endpoints(client, auth_headers):
    business_headers = auth_headers("business")

    sources = client.get("/knowledge/sources", headers=business_headers)
    assert sources.status_code == 403

    delete_response = client.post(
        "/knowledge/delete",
        headers=business_headers,
        json={"document_ids": ["fake-id"]},
    )
    assert delete_response.status_code == 403


def test_role_based_project_visibility(client, auth_headers):
    business_headers = auth_headers("business")
    procurement_headers = auth_headers("procurement")
    legal_headers = auth_headers("legal")

    created = client.post(
        "/projects",
        headers=business_headers,
        json={
            "title": "权限可见性测试",
            "requester_name": "Alice",
            "department": "Ignored by business role",
            "vendor_name": "AlphaDesk",
            "category": "software",
            "budget_amount": 1000,
            "currency": "CNY",
            "summary": "test project",
            "data_scope": "none",
        },
    )
    assert created.status_code == 200, created.text
    project_id = created.json()["id"]

    procurement_list = client.get("/projects", headers=procurement_headers)
    assert procurement_list.status_code == 200
    assert all(item["id"] != project_id for item in procurement_list.json())

    legal_list = client.get("/projects", headers=legal_headers)
    assert legal_list.status_code == 200
    assert all(item["id"] != project_id for item in legal_list.json())


def test_logout_invalidates_token(client, auth_headers):
    manager_headers = auth_headers("manager")

    me_before = client.get("/auth/me", headers=manager_headers)
    assert me_before.status_code == 200

    logout = client.post("/auth/logout", headers=manager_headers)
    assert logout.status_code == 200

    me_after = client.get("/auth/me", headers=manager_headers)
    assert me_after.status_code == 401


def test_admin_can_delete_knowledge_document(client, auth_headers):
    admin_headers = auth_headers("admin")
    upload = client.post(
        "/knowledge/upload",
        headers=admin_headers,
        files={"file": ("admin_delete_me.md", "# 删除测试\n\n这是一份待删除的知识文档。".encode("utf-8"), "text/markdown")},
        data={"allowed_roles": "employee,admin", "tags": "sample,manual"},
    )
    assert upload.status_code == 200, upload.text
    document_id = upload.json()["source"]["id"]

    delete_response = client.post(
        "/knowledge/delete",
        headers=admin_headers,
        json={"document_ids": [document_id]},
    )
    assert delete_response.status_code == 200, delete_response.text
    payload = delete_response.json()
    assert payload["deleted"] == 1
    assert payload["protected_titles"] == []

    sources = client.get("/knowledge/sources", headers=admin_headers)
    assert sources.status_code == 200
    assert all(item["id"] != document_id for item in sources.json())
