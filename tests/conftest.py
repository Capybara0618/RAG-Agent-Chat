from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import build_settings
from app.main import create_app


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "test.db"
    storage_dir = tmp_path / "uploads"
    settings = build_settings(
        database_url=f"sqlite:///{db_path}",
        storage_dir=str(storage_dir),
        api_base_url="http://testserver",
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        handbook = Path("D:/Code/RAG+Agent项目/data/sample_handbook.md").read_bytes()
        policy = Path("D:/Code/RAG+Agent项目/data/sample_policy.md").read_bytes()
        faq = Path("D:/Code/RAG+Agent项目/data/sample_faq.csv").read_bytes()
        for name, content in [
            ("sample_handbook.md", handbook),
            ("sample_policy.md", policy),
            ("sample_faq.csv", faq),
        ]:
            response = test_client.post(
                "/knowledge/upload",
                files={"file": (name, content, "application/octet-stream")},
                data={"allowed_roles": "employee", "tags": "sample"},
            )
            assert response.status_code == 200, response.text
        yield test_client